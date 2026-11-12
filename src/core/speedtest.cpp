#include "dma2ray/net.hpp"
#include "dma2ray/vless.hpp"
#include <curl/curl.h>
#include <chrono>
#include <sstream>

namespace dma2ray::net {

static size_t discard_write_cb(void*, size_t size, size_t nmemb, void* userp) {
    size_t total = size * nmemb;
    auto* counter = static_cast<double*>(userp);
    *counter += total;
    return total;
}

SpeedResult run_speed_test(const std::string& url, int proxy_port, int timeout_sec) {
    SpeedResult res;
    CURL* curl = curl_easy_init();
    if (!curl) {
        res.error = "CURL init failed";
        return res;
    }

    std::string proxy = "http://127.0.0.1:" + std::to_string(proxy_port);
    curl_easy_setopt(curl, CURLOPT_URL, url.c_str());
    curl_easy_setopt(curl, CURLOPT_PROXY, proxy.c_str());
    curl_easy_setopt(curl, CURLOPT_TIMEOUT, timeout_sec);
    curl_easy_setopt(curl, CURLOPT_USERAGENT, "dma2ray/0.2.1");
    curl_easy_setopt(curl, CURLOPT_FOLLOWLOCATION, 1L);
    curl_easy_setopt(curl, CURLOPT_WRITEFUNCTION, discard_write_cb);
    curl_easy_setopt(curl, CURLOPT_WRITEDATA, &res.bytes);

    auto start = std::chrono::steady_clock::now();
    CURLcode code = curl_easy_perform(curl);
    auto end = std::chrono::steady_clock::now();

    res.duration = std::chrono::duration<double>(end - start).count();
    if (code == CURLE_OK || code == CURLE_OPERATION_TIMEDOUT) {
        if (res.duration > 0.05 && res.bytes > 0) {
            res.mbps = (res.bytes * 8.0) / (res.duration * 1000000.0);
        }
    } else {
        res.error = curl_easy_strerror(code);
    }
    curl_easy_cleanup(curl);
    return res;
}

std::vector<std::pair<std::string, std::string>> parse_subscription_payload(const std::string& payload) {
    std::vector<std::pair<std::string, std::string>> result;
    std::string text = payload;
    try {
        std::string dec = dma2ray::vless::base64_decode(text);
        if (dec.find("://") != std::string::npos) {
            text = dec;
        }
    } catch (...) {}

    std::istringstream stream(text);
    std::string line;
    while (std::getline(stream, line)) {
        while (!line.empty() && (line.back() == '\r' || line.back() == ' ' || line.back() == '\n')) {
            line.pop_back();
        }
        if (line.empty() || line[0] == '#') continue;
        if (line.find("://") != std::string::npos) {
            result.push_back({"", line});
        }
    }
    return result;
}

} // namespace dma2ray::net
