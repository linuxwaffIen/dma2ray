#pragma once

#include <string>
#include <filesystem>
#include <functional>

namespace dma2ray::installer {

std::string asset_filename(const std::string& kernel_type, const std::string& arch = "");

bool install_kernel(
    const std::string& kernel_type,
    const std::string& arch = "",
    std::function<void(double fraction, const std::string& message)> on_progress = nullptr
);

} // namespace dma2ray::installer
