#pragma once

#include "dma2ray/vless.hpp"
#include <nlohmann/json.hpp>

namespace dma2ray::config {

nlohmann::json build_xray_config(
    const vless::VlessProfile& profile,
    bool tun,
    int socks_port = 10808,
    int http_port = 10809,
    const std::string& log_level = "warning",
    const std::string& address_override = ""
);

} // namespace dma2ray::config
