#pragma once

#include "dma2ray/state.hpp"
#include <string>
#include <functional>
#include <filesystem>
#include <memory>
#include <atomic>
#include <thread>
#include <mutex>

namespace dma2ray::manager {

enum class State {
    Stopped,
    Starting,
    Running,
    Error
};

struct Status {
    State state = State::Stopped;
    std::string profile_id;
    bool tun = false;
    std::string message;
    std::string error;
};

class CoreManager {
public:
    explicit CoreManager(state::Store& store, std::function<void(const Status&)> on_status = nullptr);
    ~CoreManager();

    void start(const state::Profile& profile, bool tun);
    void stop();

    Status get_status() const;
    std::filesystem::path resolve_core_path(const std::string& protocol) const;

private:
    state::Store& store_;
    std::function<void(const Status&)> on_status_;
    mutable std::mutex mutex_;
    Status status_;

    pid_t child_pid_ = -1;
    std::atomic<bool> running_{false};
    std::jthread monitor_thread_;

    void set_status(const Status& s);
    void monitor_process(pid_t pid);
};

} // namespace dma2ray::manager
