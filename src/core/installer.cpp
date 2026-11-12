#include "dma2ray/installer.hpp"
#include "dma2ray/paths.hpp"
#include "dma2ray/net.hpp"

#include <cstdlib>
#include <sys/stat.h>

namespace dma2ray::installer {

std::string asset_filename(const std::string& kernel_type, const std::string& arch) {
    std::string m = arch.empty() ? paths::current_arch() : arch;
    if (kernel_type == "hysteria") {
        if (m == "x86_64" || m == "amd64") return "hysteria-linux-amd64";
        if (m == "aarch64" || m == "arm64") return "hysteria-linux-arm64";
        if (m == "armv7l") return "hysteria-linux-arm";
        return "hysteria-linux-amd64";
    }
    if (m == "x86_64" || m == "amd64") return "Xray-linux-64.zip";
    if (m == "aarch64" || m == "arm64") return "Xray-linux-arm64-v8a.zip";
    if (m == "armv7l" || m == "armv7") return "Xray-linux-arm32-v7a.zip";
    return "Xray-linux-64.zip";
}

bool install_kernel(
    const std::string& kernel_type,
    const std::string& arch,
    std::function<void(double, const std::string&)> on_progress
) {
    std::string asset = asset_filename(kernel_type, arch);
    std::string base_url;
    if (kernel_type == "hysteria") {
        base_url = "https://github.com/apernet/hysteria/releases/latest/download";
    } else if (kernel_type == "amnezia-xray") {
        base_url = "https://github.com/amnezia-vpn/amnezia-xray-core/releases/latest/download";
    } else {
        base_url = "https://github.com/XTLS/Xray-core/releases/latest/download";
    }

    std::string download_url = base_url + "/" + asset;
    auto target_dir = paths::core_dir(kernel_type, arch);
    std::filesystem::create_directories(target_dir);

    auto target_file = paths::core_path(kernel_type, arch);
    auto tmp_archive = target_dir / ("download_" + asset);

    if (on_progress) on_progress(0.1, "Загрузка " + asset + "...");
    if (!net::download_file(download_url, tmp_archive.string(), on_progress)) {
        return false;
    }

    if (kernel_type == "hysteria") {
        std::error_code ec;
        std::filesystem::rename(tmp_archive, target_file, ec);
        chmod(target_file.c_str(), 0755);
    } else {
        if (on_progress) on_progress(0.9, "Распаковка архива...");
        std::string unzip_cmd = "unzip -o -q \"" + tmp_archive.string() + "\" -d \"" + target_dir.string() + "\"";
        ::system(unzip_cmd.c_str());
        std::error_code ec;
        std::filesystem::remove(tmp_archive, ec);
        chmod(target_file.c_str(), 0755);
    }

    if (on_progress) on_progress(1.0, "Готово");
    return std::filesystem::exists(target_file);
}

} // namespace dma2ray::installer
