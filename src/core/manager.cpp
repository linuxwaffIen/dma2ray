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
#include <thread>
#include <chrono>

namespace dma2ray::manager {

static bool has_net_admin_caps(const std::filesystem::path& bin_path) {
    if (geteuid() == 0) return true;
    std::string cmd = "getcap \"" + bin_path.string() + "\" 2>/dev/null";
    FILE* p = popen(cmd.c_str(), "r");
    if (!p) return false;
    char buf[256];
    std::string out;
    while (fgets(buf, sizeof(buf), p)) {
        out += buf;
    }
    pclose(p);
    return out.find("cap_net_admin") != std::string::npos;
}

static std::string find_pkexec() {
    if (std::filesystem::exists("/usr/bin/pkexec")) return "/usr/bin/pkexec";
    if (std::filesystem::exists("/bin/pkexec")) return "/bin/pkexec";
    const char* path_env = std::getenv("PATH");
    if (path_env) {
        std::string pstr = path_env;
        size_t start = 0;
        while (start < pstr.size()) {
            size_t end = pstr.find(':', start);
            if (end == std::string::npos) end = pstr.size();
            std::filesystem::path dir = pstr.substr(start, end - start);
            if (std::filesystem::exists(dir / "pkexec")) return (dir / "pkexec").string();
            start = end + 1;
        }
    }
    return {};
}

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
    std::string custom = store_.get_string_setting("core_path", "");
    if (!custom.empty() && std::filesystem::exists(custom)) {
        return custom;
    }

    if (protocol == "hysteria") {
        auto hy_p = paths::core_path("hysteria");
        if (std::filesystem::exists(hy_p)) return hy_p;
    }

    std::string mode = store_.get_string_setting("kernel_mode", "auto");
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

    int socks_port = store_.get_int_setting("socks_port", 10808);
    int http_port = store_.get_int_setting("http_port", 10809);

    bool need_elevation = tun && (geteuid() != 0) && !has_net_admin_caps(bin);
    std::string exec_bin = bin.string();
    std::vector<std::string> args;

    if (need_elevation) {
        std::string pk = find_pkexec();
        if (pk.empty()) {
            s.state = State::Error;
            s.error = "Для режима «ВПН (TUN)» требуется root или pkexec (polkit). Переключитесь на «Системный прокси» или установите polkit.";
            set_status(s);
            return;
        }
        exec_bin = pk;
        args.push_back("pkexec");
        args.push_back(bin.string());
    } else {
        args.push_back(bin.string());
    }

    if (is_hy) {
        auto hy_prof = hysteria::parse_hysteria2(profile.uri);
        std::string yaml = hysteria::format_hysteria_yaml(hy_prof, socks_port, http_port, tun);
        std::ofstream(paths::hy_config_file()) << yaml;
        args.push_back("client");
        args.push_back("-c");
        args.push_back(paths::hy_config_file().string());
    } else {
        auto vless_prof = vless::parse_any_vless(profile.uri);
        auto xray_cfg = config::build_xray_config(vless_prof, tun, socks_port, http_port);
        std::ofstream(paths::config_file()) << xray_cfg.dump(2);
        args.push_back("run");
        args.push_back("-c");
        args.push_back(paths::config_file().string());
    }

    pid_t pid = fork();
    if (pid == 0) {
        // Child
        int null_fd = open("/dev/null", O_RDONLY);
        if (null_fd >= 0) {
            dup2(null_fd, STDIN_FILENO);
            close(null_fd);
        }

        int log_fd = open(paths::log_file().c_str(), O_WRONLY | O_CREAT | O_TRUNC, 0644);
        if (log_fd >= 0) {
            dup2(log_fd, STDOUT_FILENO);
            dup2(log_fd, STDERR_FILENO);
            close(log_fd);
        }

        std::vector<char*> c_args;
        for (auto& a : args) c_args.push_back(const_cast<char*>(a.c_str()));
        c_args.push_back(nullptr);

        execvp(exec_bin.c_str(), c_args.data());
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
        s.profile_id = status_.profile_id;

        std::string err_msg;
        std::ifstream lf(paths::log_file());
        if (lf.is_open()) {
            std::string line;
            std::vector<std::string> lines;
            while (std::getline(lf, line)) {
                if (!line.empty()) lines.push_back(line);
            }
            for (auto it = lines.rbegin(); it != lines.rend(); ++it) {
                if (it->find("failed to start") != std::string::npos ||
                    it->find("operation not permitted") != std::string::npos ||
                    it->find("permission denied") != std::string::npos ||
                    it->find("error") != std::string::npos ||
                    it->find("Error") != std::string::npos ||
                    it->find("FATAL") != std::string::npos) {
                    err_msg = *it;
                    break;
                }
            }
        }
        if (err_msg.empty()) {
            err_msg = "Процесс ядра завершился с кодом " + std::to_string(WEXITSTATUS(status));
        }
        s.error = err_msg;
        set_status(s);
        running_ = false;
        child_pid_ = -1;
    }
}

void CoreManager::stop() {
    running_ = false;
    if (child_pid_ > 0) {
        kill(child_pid_, SIGTERM);
        for (int i = 0; i < 20; ++i) {
            int status = 0;
            pid_t res = waitpid(child_pid_, &status, WNOHANG);
            if (res != 0) break;
            std::this_thread::sleep_for(std::chrono::milliseconds(100));
        }
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
