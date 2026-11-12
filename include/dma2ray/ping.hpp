#pragma once

#include <string>
#include <optional>

namespace dma2ray::ping {

std::optional<int> tcp_ping(const std::string& host, int port, double timeout_sec = 4.0);
std::optional<int> http_ping(const std::string& host, int port, bool use_tls = false, double timeout_sec = 4.0);
std::optional<int> icmp_ping(const std::string& host, double timeout_sec = 4.0);

std::optional<int> ping_endpoint(
    const std::string& host,
    int port,
    const std::string& ping_type = "tcp",
    double timeout_sec = 4.0,
    bool use_tls = false
);

} // namespace dma2ray::ping
