#include "dma2ray/vless.hpp"

#include <stdexcept>
#include <sstream>
#include <algorithm>
#include <cctype>

namespace dma2ray::vless {

std::string url_decode(const std::string& in) {
    std::string out;
    out.reserve(in.size());
    for (size_t i = 0; i < in.size(); ++i) {
        if (in[i] == '%' && i + 2 < in.size()) {
            int value;
            std::istringstream is(in.substr(i + 1, 2));
            if (is >> std::hex >> value) {
                out.push_back(static_cast<char>(value));
                i += 2;
            } else {
                out.push_back(in[i]);
            }
        } else if (in[i] == '+') {
            out.push_back(' ');
        } else {
            out.push_back(in[i]);
        }
    }
    return out;
}

static const std::string base64_chars = 
             "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
             "abcdefghijklmnopqrstuvwxyz"
             "0123456789+/";

std::string base64_decode(const std::string& in) {
    std::string clean = in;
    clean.erase(std::remove_if(clean.begin(), clean.end(), [](unsigned char c) {
        return std::isspace(c);
    }), clean.end());
    // URL safe replace
    for (char& c : clean) {
        if (c == '-') c = '+';
        else if (c == '_') c = '/';
    }
    while (clean.size() % 4 != 0) clean.push_back('=');

    std::string out;
    std::vector<int> T(256, -1);
    for (int i = 0; i < 64; i++) T[base64_chars[i]] = i;

    int val = 0, valb = -8;
    for (unsigned char c : clean) {
        if (T[c] == -1) break;
        val = (val << 6) + T[c];
        valb += 6;
        if (valb >= 0) {
            out.push_back(char((val >> valb) & 0xFF));
            valb -= 8;
        }
    }
    return out;
}

static std::map<std::string, std::string> parse_query(const std::string& query) {
    std::map<std::string, std::string> res;
    std::istringstream stream(query);
    std::string pair;
    while (std::getline(stream, pair, '&')) {
        size_t eq = pair.find('=');
        if (eq != std::string::npos) {
            res[url_decode(pair.substr(0, eq))] = url_decode(pair.substr(eq + 1));
        } else if (!pair.empty()) {
            res[url_decode(pair)] = "";
        }
    }
    return res;
}

VlessProfile parse_vless(const std::string& uri) {
    if (uri.rfind("vless://", 0) != 0) {
        throw std::runtime_error("Invalid VLESS prefix");
    }
    std::string rest = uri.substr(8);
    VlessProfile p;
    p.protocol = "vless";

    size_t hash_pos = rest.find('#');
    if (hash_pos != std::string::npos) {
        p.name = url_decode(rest.substr(hash_pos + 1));
        rest = rest.substr(0, hash_pos);
    }

    size_t q_pos = rest.find('?');
    std::map<std::string, std::string> query;
    if (q_pos != std::string::npos) {
        query = parse_query(rest.substr(q_pos + 1));
        rest = rest.substr(0, q_pos);
    }

    size_t at_pos = rest.find('@');
    if (at_pos == std::string::npos) throw std::runtime_error("Missing @ in VLESS URI");
    p.uuid = url_decode(rest.substr(0, at_pos));
    std::string host_port = rest.substr(at_pos + 1);

    size_t colon_pos = host_port.rfind(':');
    if (colon_pos == std::string::npos) throw std::runtime_error("Missing port in VLESS URI");
    p.address = host_port.substr(0, colon_pos);
    if (!p.address.empty() && p.address.front() == '[' && p.address.back() == ']') {
        p.address = p.address.substr(1, p.address.size() - 2);
    }
    p.port = std::stoi(host_port.substr(colon_pos + 1));

    if (query.count("security")) p.security = query["security"];
    if (query.count("encryption")) p.encryption = query["encryption"];
    if (query.count("flow")) p.flow = query["flow"];
    if (query.count("sni")) p.sni = query["sni"];
    if (query.count("fp")) p.fp = query["fp"];
    if (query.count("pbk")) p.pbk = query["pbk"];
    if (query.count("sid")) p.sid = query["sid"];
    if (query.count("spx")) p.spx = query["spx"];
    if (query.count("type")) p.network = query["type"];
    if (query.count("headerType")) p.header_type = query["headerType"];
    if (query.count("host")) p.host_header = query["host"];
    if (query.count("path")) p.path = query["path"];
    if (query.count("serviceName")) p.service_name = query["serviceName"];
    if (query.count("mode")) p.mode = query["mode"];

    return p;
}

VlessProfile parse_trojan(const std::string& uri) {
    if (uri.rfind("trojan://", 0) != 0) throw std::runtime_error("Invalid Trojan prefix");
    std::string copy = "vless://" + uri.substr(9);
    VlessProfile p = parse_vless(copy);
    p.protocol = "trojan";
    if (p.security.empty() || p.security == "none") p.security = "tls";
    return p;
}

VlessProfile parse_shadowsocks(const std::string& uri) {
    if (uri.rfind("ss://", 0) != 0) throw std::runtime_error("Invalid SS prefix");
    std::string rest = uri.substr(5);
    VlessProfile p;
    p.protocol = "shadowsocks";

    size_t hash_pos = rest.find('#');
    if (hash_pos != std::string::npos) {
        p.name = url_decode(rest.substr(hash_pos + 1));
        rest = rest.substr(0, hash_pos);
    }

    size_t at_pos = rest.find('@');
    if (at_pos == std::string::npos) {
        // base64 encoded user:pass@host:port
        std::string dec = base64_decode(rest);
        return parse_shadowsocks("ss://" + dec + (p.name.empty() ? "" : "#" + p.name));
    }

    std::string user_info = rest.substr(0, at_pos);
    if (user_info.find(':') == std::string::npos) {
        user_info = base64_decode(user_info);
    }
    size_t sec_colon = user_info.find(':');
    if (sec_colon != std::string::npos) {
        p.security = user_info.substr(0, sec_colon);
        p.uuid = user_info.substr(sec_colon + 1);
    } else {
        p.uuid = user_info;
    }

    std::string host_port = rest.substr(at_pos + 1);
    size_t colon_pos = host_port.rfind(':');
    if (colon_pos == std::string::npos) throw std::runtime_error("Missing port in SS URI");
    p.address = host_port.substr(0, colon_pos);
    p.port = std::stoi(host_port.substr(colon_pos + 1));
    return p;
}

VlessProfile parse_vmess(const std::string& uri) {
    if (uri.rfind("vmess://", 0) != 0) throw std::runtime_error("Invalid VMess prefix");
    std::string b64 = uri.substr(8);
    std::string dec = base64_decode(b64);
    auto j = nlohmann::json::parse(dec);

    VlessProfile p;
    p.protocol = "vmess";
    p.address = j.value("add", "");
    p.port = j.value("port", 443);
    p.uuid = j.value("id", "");
    p.name = j.value("ps", "");
    p.network = j.value("net", "tcp");
    p.path = j.value("path", "");
    p.host_header = j.value("host", "");
    p.security = j.value("tls", "none");
    p.sni = j.value("sni", "");
    return p;
}

VlessProfile parse_any_vless(const std::string& uri) {
    if (uri.rfind("vless://", 0) == 0) return parse_vless(uri);
    if (uri.rfind("vmess://", 0) == 0) return parse_vmess(uri);
    if (uri.rfind("trojan://", 0) == 0) return parse_trojan(uri);
    if (uri.rfind("ss://", 0) == 0) return parse_shadowsocks(uri);
    throw std::runtime_error("Unsupported URI format");
}

nlohmann::json VlessProfile::to_xray_outbound() const {
    nlohmann::json out;
    out["tag"] = "proxy";
    out["protocol"] = protocol;

    nlohmann::json settings;
    if (protocol == "vless") {
        nlohmann::json vnext = nlohmann::json::array();
        nlohmann::json user;
        user["id"] = uuid;
        user["encryption"] = encryption.empty() ? "none" : encryption;
        if (!flow.empty()) user["flow"] = flow;

        nlohmann::json server;
        server["address"] = address;
        server["port"] = port;
        server["users"] = nlohmann::json::array({user});
        vnext.push_back(server);
        settings["vnext"] = vnext;
    } else if (protocol == "trojan") {
        nlohmann::json servers = nlohmann::json::array();
        nlohmann::json server;
        server["address"] = address;
        server["port"] = port;
        server["password"] = uuid;
        servers.push_back(server);
        settings["servers"] = servers;
    } else if (protocol == "shadowsocks") {
        nlohmann::json servers = nlohmann::json::array();
        nlohmann::json server;
        server["address"] = address;
        server["port"] = port;
        server["method"] = security;
        server["password"] = uuid;
        servers.push_back(server);
        settings["servers"] = servers;
    }
    out["settings"] = settings;
    out["streamSettings"] = to_xray_stream();
    return out;
}

nlohmann::json VlessProfile::to_xray_stream() const {
    nlohmann::json s;
    s["network"] = network;
    s["security"] = security;

    if (security == "tls") {
        nlohmann::json tls;
        if (!sni.empty()) tls["serverName"] = sni;
        if (!fp.empty()) tls["fingerprint"] = fp;
        s["tlsSettings"] = tls;
    } else if (security == "reality") {
        nlohmann::json reality;
        if (!sni.empty()) reality["serverName"] = sni;
        if (!fp.empty()) reality["fingerprint"] = fp;
        if (!pbk.empty()) reality["publicKey"] = pbk;
        if (!sid.empty()) reality["shortId"] = sid;
        if (!spx.empty()) reality["spiderX"] = spx;
        s["realitySettings"] = reality;
    }

    if (network == "ws") {
        nlohmann::json ws;
        ws["path"] = path.empty() ? "/" : path;
        if (!host_header.empty()) ws["headers"]["Host"] = host_header;
        s["wsSettings"] = ws;
    } else if (network == "grpc") {
        nlohmann::json grpc;
        grpc["serviceName"] = service_name;
        if (mode == "multi" || mode == "multimode") grpc["multiMode"] = true;
        s["grpcSettings"] = grpc;
    } else if (network == "xhttp") {
        nlohmann::json xhttp;
        xhttp["path"] = path.empty() ? "/" : path;
        if (!host_header.empty()) xhttp["host"] = host_header;
        if (!mode.empty()) xhttp["mode"] = mode;
        s["xhttpSettings"] = xhttp;
    }
    return s;
}

} // namespace dma2ray::vless
