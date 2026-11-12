#include "dma2ray/hysteria.hpp"
#include "dma2ray/vless.hpp"

#include <stdexcept>
#include <sstream>

namespace dma2ray::hysteria {

HysteriaProfile parse_hysteria2(const std::string& uri) {
    if (uri.rfind("hysteria2://", 0) != 0 && uri.rfind("hy2://", 0) != 0) {
        throw std::runtime_error("Invalid Hysteria2 prefix");
    }
    size_t prefix_len = uri.rfind("hysteria2://", 0) == 0 ? 12 : 6;
    std::string rest = uri.substr(prefix_len);

    HysteriaProfile p;
    size_t hash_pos = rest.find('#');
    if (hash_pos != std::string::npos) {
        p.name = dma2ray::vless::url_decode(rest.substr(hash_pos + 1));
        rest = rest.substr(0, hash_pos);
    }

    size_t q_pos = rest.find('?');
    std::string query_str;
    if (q_pos != std::string::npos) {
        query_str = rest.substr(q_pos + 1);
        rest = rest.substr(0, q_pos);
    }

    size_t at_pos = rest.find('@');
    if (at_pos != std::string::npos) {
        p.auth = dma2ray::vless::url_decode(rest.substr(0, at_pos));
        rest = rest.substr(at_pos + 1);
    }

    size_t colon_pos = rest.rfind(':');
    if (colon_pos == std::string::npos) {
        p.address = rest;
        p.port = 443;
    } else {
        p.address = rest.substr(0, colon_pos);
        p.port = std::stoi(rest.substr(colon_pos + 1));
    }

    if (!query_str.empty()) {
        std::istringstream stream(query_str);
        std::string pair;
        while (std::getline(stream, pair, '&')) {
            size_t eq = pair.find('=');
            if (eq != std::string::npos) {
                std::string k = dma2ray::vless::url_decode(pair.substr(0, eq));
                std::string v = dma2ray::vless::url_decode(pair.substr(eq + 1));
                if (k == "sni") p.sni = v;
                else if (k == "insecure") p.insecure = (v == "1" || v == "true");
                else if (k == "obfs") p.obfs = v;
                else if (k == "obfs-password") p.obfs_password = v;
            }
        }
    }

    return p;
}

std::string format_hysteria_yaml(const HysteriaProfile& p, int socks_port, int http_port, bool tun) {
    std::ostringstream out;
    out << "server: " << p.address << ":" << p.port << "\n";
    if (!p.auth.empty()) {
        out << "auth: " << p.auth << "\n";
    }
    out << "tls:\n";
    out << "  sni: " << (p.sni.empty() ? p.address : p.sni) << "\n";
    if (p.insecure) {
        out << "  insecure: true\n";
    }
    out << "socks5:\n";
    out << "  listen: 127.0.0.1:" << socks_port << "\n";
    out << "http:\n";
    out << "  listen: 127.0.0.1:" << http_port << "\n";

    if (!p.obfs.empty()) {
        out << "obfs:\n";
        out << "  type: " << p.obfs << "\n";
        if (!p.obfs_password.empty()) {
            out << "  salamander:\n";
            out << "    password: " << p.obfs_password << "\n";
        }
    }

    if (tun) {
        out << "tun:\n";
        out << "  name: dma2ray-tun\n";
        out << "  timeout: 300s\n";
    }
    return out.str();
}

} // namespace dma2ray::hysteria
