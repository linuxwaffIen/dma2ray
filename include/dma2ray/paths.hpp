#pragma once

#include <filesystem>
#include <string>

namespace dma2ray::paths {

extern const std::string APP_ID;
extern const std::string APP_TITLE;
extern const std::string VERSION;

std::filesystem::path config_dir();
std::filesystem::path cache_dir();
std::filesystem::path data_dir();

std::filesystem::path state_file();
std::filesystem::path config_file();
std::filesystem::path hy_config_file();
std::filesystem::path log_file();
std::filesystem::path priv_socket();

std::filesystem::path core_bin_dir();
std::filesystem::path icons_dir();
std::filesystem::path core_dir(const std::string& kernel_type = "xray", const std::string& arch = "");
std::filesystem::path core_path(const std::string& kernel_type = "xray", const std::string& arch = "");

void ensure_dirs();
void ensure_icons();
std::string current_arch();

} // namespace dma2ray::paths
