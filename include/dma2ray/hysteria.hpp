#pragma once

#include <string>

namespace dma2ray::hysteria {

struct HysteriaProfile {
    std::string address;
    int port = 443;
    std::string auth;
    std::string sni;
    bool insecure = false;
    std::string obfs;
    std::string obfs_password;
    std::string name;
    std::string protocol = "hysteria";
};

HysteriaProfile parse_hysteria2(const std::string& uri);
std::string format_hysteria_yaml(const HysteriaProfile& p, int socks_port, int http_port, bool tun);

} // namespace dma2ray::hysteria
