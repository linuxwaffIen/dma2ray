#include "dma2ray/ping.hpp"

#include <sys/types.h>
#include <sys/socket.h>
#include <netdb.h>
#include <unistd.h>
#include <fcntl.h>
#include <poll.h>
#include <chrono>
#include <cmath>
#include <array>
#include <memory>
#include <openssl/ssl.h>
#include <openssl/err.h>

namespace dma2ray::ping {

std::optional<int> tcp_ping(const std::string& host, int port, double timeout_sec) {
    struct addrinfo hints{}, *res = nullptr;
    hints.ai_family = AF_UNSPEC;
    hints.ai_socktype = SOCK_STREAM;

    std::string port_str = std::to_string(port);
    if (getaddrinfo(host.c_str(), port_str.c_str(), &hints, &res) != 0 || !res) {
        return std::nullopt;
    }

    auto start = std::chrono::steady_clock::now();
    int sock = -1;
    for (struct addrinfo* p = res; p != nullptr; p = p->ai_next) {
        sock = socket(p->ai_family, p->ai_socktype, p->ai_protocol);
        if (sock < 0) continue;

        int flags = fcntl(sock, F_GETFL, 0);
        fcntl(sock, F_SETFL, flags | O_NONBLOCK);

        int ret = connect(sock, p->ai_addr, p->ai_addrlen);
        if (ret == 0) {
            close(sock);
            freeaddrinfo(res);
            auto end = std::chrono::steady_clock::now();
            return std::max(1, static_cast<int>(std::chrono::duration<double, std::milli>(end - start).count()));
        }

        struct pollfd pfd{};
        pfd.fd = sock;
        pfd.events = POLLOUT;
        int p_ret = poll(&pfd, 1, static_cast<int>(timeout_sec * 1000));
        if (p_ret > 0 && (pfd.revents & POLLOUT)) {
            int err = 0;
            socklen_t len = sizeof(err);
            getsockopt(sock, SOL_SOCKET, SO_ERROR, &err, &len);
            if (err == 0) {
                close(sock);
                freeaddrinfo(res);
                auto end = std::chrono::steady_clock::now();
                return std::max(1, static_cast<int>(std::chrono::duration<double, std::milli>(end - start).count()));
            }
        }
        close(sock);
    }
    freeaddrinfo(res);
    return std::nullopt;
}

std::optional<int> http_ping(const std::string& host, int port, bool use_tls, double timeout_sec) {
    struct addrinfo hints{}, *res = nullptr;
    hints.ai_family = AF_UNSPEC;
    hints.ai_socktype = SOCK_STREAM;

    std::string port_str = std::to_string(port);
    if (getaddrinfo(host.c_str(), port_str.c_str(), &hints, &res) != 0 || !res) {
        return std::nullopt;
    }

    int sock = socket(res->ai_family, res->ai_socktype, res->ai_protocol);
    if (sock < 0) {
        freeaddrinfo(res);
        return std::nullopt;
    }

    struct timeval tv{};
    tv.tv_sec = static_cast<time_t>(timeout_sec);
    tv.tv_usec = static_cast<suseconds_t>((timeout_sec - tv.tv_sec) * 1e6);
    setsockopt(sock, SOL_SOCKET, SO_RCVTIMEO, &tv, sizeof(tv));
    setsockopt(sock, SOL_SOCKET, SO_SNDTIMEO, &tv, sizeof(tv));

    auto start = std::chrono::steady_clock::now();
    if (connect(sock, res->ai_addr, res->ai_addrlen) != 0) {
        close(sock);
        freeaddrinfo(res);
        return std::nullopt;
    }
    freeaddrinfo(res);

    std::string req = "GET / HTTP/1.1\r\nHost: " + host + "\r\nUser-Agent: dma2ray\r\nConnection: close\r\n\r\n";
    if (use_tls) {
        SSL_library_init();
        SSL_CTX* ctx = SSL_CTX_new(TLS_client_method());
        SSL* ssl = SSL_new(ctx);
        SSL_set_fd(ssl, sock);
        SSL_set_tlsext_host_name(ssl, host.c_str());
        if (SSL_connect(ssl) <= 0) {
            SSL_free(ssl);
            SSL_CTX_free(ctx);
            close(sock);
            return std::nullopt;
        }
        SSL_write(ssl, req.c_str(), static_cast<int>(req.size()));
        char buf[128];
        int r = SSL_read(ssl, buf, sizeof(buf));
        SSL_shutdown(ssl);
        SSL_free(ssl);
        SSL_CTX_free(ctx);
        close(sock);
        if (r <= 0) return std::nullopt;
    } else {
        send(sock, req.c_str(), req.size(), 0);
        char buf[128];
        ssize_t r = recv(sock, buf, sizeof(buf), 0);
        close(sock);
        if (r <= 0) return std::nullopt;
    }

    auto end = std::chrono::steady_clock::now();
    return std::max(1, static_cast<int>(std::chrono::duration<double, std::milli>(end - start).count()));
}

std::optional<int> icmp_ping(const std::string& host, double timeout_sec) {
    std::string cmd = "ping -c 1 -W " + std::to_string(std::max(1, static_cast<int>(timeout_sec))) + " " + host + " 2>/dev/null";
    FILE* pipe = popen(cmd.c_str(), "r");
    if (!pipe) return std::nullopt;

    std::array<char, 256> buf;
    std::string result;
    while (fgets(buf.data(), buf.size(), pipe) != nullptr) {
        result += buf.data();
    }
    int code = pclose(pipe);
    if (code != 0) return std::nullopt;

    size_t pos = result.find("time=");
    if (pos != std::string::npos) {
        size_t end_pos = result.find(" ms", pos);
        if (end_pos != std::string::npos) {
            try {
                float ms = std::stof(result.substr(pos + 5, end_pos - (pos + 5)));
                return static_cast<int>(std::round(ms));
            } catch (...) {}
        }
    }
    return std::nullopt;
}

std::optional<int> ping_endpoint(
    const std::string& host,
    int port,
    const std::string& ping_type,
    double timeout_sec,
    bool use_tls
) {
    if (ping_type == "icmp") return icmp_ping(host, timeout_sec);
    if (ping_type == "http") return http_ping(host, port, use_tls, timeout_sec);
    return tcp_ping(host, port, timeout_sec);
}

} // namespace dma2ray::ping
