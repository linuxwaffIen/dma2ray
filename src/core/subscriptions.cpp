#include "dma2ray/net.hpp"
#include "dma2ray/vless.hpp"

#include <curl/curl.h>
#include <fstream>
#include <chrono>
#include <sstream>

namespace dma2ray::net {

static size_t string_write_cb(void* contents, size_t size, size_t nmemb, void* userp) {
    size_t total = size * nmemb;
    auto* str = static_cast<std::string*>(userp);
    str->append(static_cast<char*>(contents), total);
    return total;
}

FetchResult http_get(const std::string& url, int timeout_sec, const std::string& proxy) {
    FetchResult res;
    CURL* curl = curl_easy_init();
    if (!curl) {
        res.error = "Failed to initialize CURL";
        return res;
    }

    curl_easy_setopt(curl, CURLOPT_URL, url.c_str());
    curl_easy_setopt(curl, CURLOPT_TIMEOUT, timeout_sec);
    curl_easy_setopt(curl, CURLOPT_USERAGENT, "dma2ray/0.2.1");
    curl_easy_setopt(curl, CURLOPT_FOLLOWLOCATION, 1L);
    curl_easy_setopt(curl, CURLOPT_WRITEFUNCTION, string_write_cb);
    curl_easy_setopt(curl, CURLOPT_WRITEDATA, &res.data);

    if (!proxy.empty()) {
        curl_easy_setopt(curl, CURLOPT_PROXY, proxy.c_str());
    }

    CURLcode code = curl_easy_perform(curl);
    if (code == CURLE_OK) {
        res.success = true;
    } else {
        res.error = curl_easy_strerror(code);
    }
    curl_easy_cleanup(curl);
    return res;
}

struct ProgressContext {
    std::function<void(double, const std::string&)> cb;
};

static int xferinfo_cb(void* clientp, curl_off_t dltotal, curl_off_t dlnow, curl_off_t, curl_off_t) {
    auto* ctx = static_cast<ProgressContext*>(clientp);
    if (ctx && ctx->cb && dltotal > 0) {
        double fraction = static_cast<double>(dlnow) / static_cast<double>(dltotal);
        ctx->cb(fraction, "Загрузка...");
    }
    return 0;
}

static size_t file_write_cb(void* ptr, size_t size, size_t nmemb, void* stream) {
    auto* file = static_cast<std::ofstream*>(stream);
    file->write(static_cast<char*>(ptr), size * nmemb);
    return size * nmemb;
}

bool download_file(
    const std::string& url,
    const std::string& dest_path,
    std::function<void(double, const std::string&)> on_progress
) {
    std::ofstream ofs(dest_path, std::ios::binary);
    if (!ofs.is_open()) return false;

    CURL* curl = curl_easy_init();
    if (!curl) return false;

    ProgressContext ctx{on_progress};
    curl_easy_setopt(curl, CURLOPT_URL, url.c_str());
    curl_easy_setopt(curl, CURLOPT_FOLLOWLOCATION, 1L);
    curl_easy_setopt(curl, CURLOPT_WRITEFUNCTION, file_write_cb);
    curl_easy_setopt(curl, CURLOPT_WRITEDATA, &ofs);
    curl_easy_setopt(curl, CURLOPT_USERAGENT, "dma2ray/0.2.1");

    if (on_progress) {
        curl_easy_setopt(curl, CURLOPT_NOPROGRESS, 0L);
        curl_easy_setopt(curl, CURLOPT_XFERINFOFUNCTION, xferinfo_cb);
        curl_easy_setopt(curl, CURLOPT_XFERINFODATA, &ctx);
    }

    CURLcode code = curl_easy_perform(curl);
    curl_easy_cleanup(curl);
    ofs.close();
    return code == CURLE_OK;
}

} // namespace dma2ray::net
