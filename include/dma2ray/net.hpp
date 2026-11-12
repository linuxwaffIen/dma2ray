#pragma once

#include <string>
#include <vector>
#include <functional>

namespace dma2ray::net {

struct FetchResult {
    bool success = false;
    std::string data;
    std::string error;
};

FetchResult http_get(const std::string& url, int timeout_sec = 15, const std::string& proxy = "");

bool download_file(
    const std::string& url,
    const std::string& dest_path,
    std::function<void(double fraction, const std::string& msg)> on_progress = nullptr
);

struct SpeedResult {
    double mbps = 0.0;
    double bytes = 0.0;
    double duration = 0.0;
    std::string error;
};

SpeedResult run_speed_test(
    const std::string& url = "https://speed.cloudflare.com/__down?bytes=25000000",
    int proxy_port = 10809,
    int timeout_sec = 10
);

std::vector<std::pair<std::string, std::string>> parse_subscription_payload(const std::string& payload);

} // namespace dma2ray::net
