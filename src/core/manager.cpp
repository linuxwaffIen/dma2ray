#include "dma2ray/manager.hpp"
#include "dma2ray/paths.hpp"
#include "dma2ray/config.hpp"
#include "dma2ray/hysteria.hpp"
#include "dma2ray/vless.hpp"

#include <sys/types.h>
#include <sys/stat.h>
#include <fcntl.h>
#include <sys/wait.h>
#include <signal.h>
#include <unistd.h>
#include <fstream>

namespace dma2ray::manager {

CoreManager::CoreManager(state::Store& store, std::function<void(const Status&)> on_status)
    : store_(store), on_status_(on_status) {}

CoreManager::~CoreManager() {
    stop();
}

void CoreManager::set_status(const Status& s) {
    {
        std::lock_guard<std::mutex> lock(mutex_);
        status_ = s;
    }
    if (on_status_) on_status_(s);
}

Status CoreManager::get_status() const {
    std::lock_guard<std::mutex> lock(mutex_);
    return status_;
}

std::filesystem::path CoreManager::resolve_core_path(const std::string& protocol) const {
    std::string custom = store_.get_setting("core_path", "").get<std::string>();
    if (!custom.empty() && std::filesystem::exists(custom)) {
        return custom;
    }

    if (protocol == "hysteria") {
        auto hy_p = paths::core_path("hysteria");
        if (std::filesystem::exists(hy_p)) return hy_p;
    }

    std::string mode = store_.get_setting("kernel_mode", "auto").get<std::string>();
    if (mode == "amnezia-xray" || (mode == "auto" && protocol == "wireguard")) {
        auto amn = paths::core_path("amnezia-xray");
        if (std::filesystem::exists(amn)) return amn;
    }

    auto xray = paths::core_path("xray");
    if (std::filesystem::exists(xray)) return xray;

    // Check system PATH
    const char* path_env = std::getenv("PATH");
    if (path_env) {
        std::string pstr = path_env;
        size_t start = 0;
        while (start < pstr.size()) {
            size_t end = pstr.find(':', start);
            if (end == std::string::npos) end = pstr.size();
            std::filesystem::path dir = pstr.substr(start, end - start);
            if (std::filesystem::exists(dir / "xray")) return dir / "xray";
            start = end + 1;
        }
    }
    return {};
}

void CoreManager::start(const state::Profile& profile, bool tun) {
    stop();

    Status s;
    s.state = State::Starting;
    s.profile_id = profile.id;
    s.tun = tun;
    s.message = "Запуск ядра...";
    set_status(s);

    paths::ensure_dirs();
    bool is_hy = profile.uri.rfind("hysteria2://", 0) == 0 || profile.uri.rfind("hy2://", 0) == 0;
    std::string protocol = is_hy ? "hysteria" : (profile.uri.rfind("wireguard://", 0) == 0 ? "wireguard" : "vless");

    std::filesystem::path bin = resolve_core_path(protocol);
    if (bin.empty() || !std::filesystem::exists(bin)) {
        s.state = State::Error;
        s.error = "Ядро не найдено. Скачайте его в меню «Ядра».";
        set_status(s);
        return;
    }

    int socks_port = store_.get_setting("socks_port", 10808).get<int>();
    int http_port = store_.get_setting("http_port", 10809).get<int>();

    std::vector<std::string> args;
    if (is_hy) {
        auto hy_prof = hysteria::parse_hysteria2(profile.uri);
        std::string yaml = hysteria::format_hysteria_yaml(hy_prof, socks_port, http_port, tun);
        std::ofstream(paths::hy_config_file()) << yaml;
        args = {bin.string(), "client", "-c", paths::hy_config_file().string()};
    } else {
        auto vless_prof = vless::parse_any_vless(profile.uri);
        auto xray_cfg = config::build_xray_config(vless_prof, tun, socks_port, http_port);
        std::ofstream(paths::config_file()) << xray_cfg.dump(2);
        args = {bin.string(), "run", "-c", paths::config_file().string()};
    }

    pid_t pid = fork();
    if (pid == 0) {
        // Child
        std::vector<char*> c_args;
        for (auto& a : args) c_args.push_back(const_cast<char*>(a.c_str()));
        c_args.push_back(nullptr);

        int log_fd = open(paths::log_file().c_str(), O_WRONLY | O_CREAT | O_TRUNC, 0644);
        if (log_fd >= 0) {
            dup2(log_fd, STDOUT_FILENO);
            dup2(log_fd, STDERR_FILENO);
            close(log_fd);
        }
        execv(bin.c_str(), c_args.data());
        _exit(127);
    } else if (pid > 0) {
        child_pid_ = pid;
        running_ = true;
        s.state = State::Running;
        s.message = "Подключено";
        set_status(s);

        monitor_thread_ = std::jthread([this, pid]() {
            monitor_process(pid);
        });
    } else {
        s.state = State::Error;
        s.error = "Ошибка запуска процесса ядра fork()";
        set_status(s);
    }
}

void CoreManager::monitor_process(pid_t pid) {
    int status = 0;
    waitpid(pid, &status, 0);

    if (running_.load()) {
        Status s;
        s.state = State::Error;
        s.error = "Процесс ядра неожиданно завершился (код " + std::to_string(WEXITSTATUS(status)) + ")";
        set_status(s);
        running_ = false;
        child_pid_ = -1;
    }
}

void CoreManager::stop() {
    running_ = false;
    if (child_pid_ > 0) {
        kill(child_pid_, SIGTERM);
        usleep(100000);
        kill(child_pid_, SIGKILL);
        int status;
        waitpid(child_pid_, &status, WNOHANG);
        child_pid_ = -1;
    }
    if (monitor_thread_.joinable()) {
        monitor_thread_.join();
    }
    Status s;
    s.state = State::Stopped;
    s.message = "Отключено";
    set_status(s);
}

} // namespace dma2ray::manager
