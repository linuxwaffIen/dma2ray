#pragma once

#include <string>
#include <vector>
#include <map>
#include <nlohmann/json.hpp>

namespace dma2ray::vless {

struct VlessProfile {
    std::string protocol = "vless";
    std::string uuid;
    std::string address;
    int port = 443;
    std::string encryption = "none";
    std::string flow;
    std::string security = "none";
    std::string sni;
    std::string fp;
    std::string pbk;
    std::string sid;
    std::string spx;
    std::string network = "tcp";
    std::string header_type;
    std::string host_header;
    std::string path;
    std::string service_name;
    std::string mode;
    std::string name;
    
    // WireGuard / Amnezia specifics
    int jc = 0;
    int jmin = 0;
    int jmax = 0;
    int s1 = 0;
    int s2 = 0;
    int h1 = 0;
    int h2 = 0;
    int h3 = 0;
    int h4 = 0;

    nlohmann::json to_xray_outbound() const;
    nlohmann::json to_xray_stream() const;
};

VlessProfile parse_vless(const std::string& uri);
VlessProfile parse_vmess(const std::string& uri);
VlessProfile parse_trojan(const std::string& uri);
VlessProfile parse_shadowsocks(const std::string& uri);
VlessProfile parse_wireguard(const std::string& uri);

VlessProfile parse_any_vless(const std::string& uri);

std::string url_decode(const std::string& in);
std::string base64_decode(const std::string& in);

} // namespace dma2ray::vless
