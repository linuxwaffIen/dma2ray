#include "dma2ray/flags.hpp"
#include <unordered_map>
#include <algorithm>
#include <cctype>

namespace dma2ray::flags {

static const std::unordered_map<std::string, std::string> CODE_FLAGS = {
    {"at", "🇦🇹"}, {"au", "🇦🇺"}, {"be", "🇧🇪"}, {"bg", "🇧🇬"}, {"br", "🇧🇷"},
    {"ca", "🇨🇦"}, {"ch", "🇨🇭"}, {"cz", "🇨🇿"}, {"de", "🇩🇪"}, {"dk", "🇩🇰"},
    {"ee", "🇪🇪"}, {"es", "🇪🇸"}, {"fi", "🇫🇮"}, {"fr", "🇫🇷"}, {"gb", "🇬🇧"},
    {"gr", "🇬🇷"}, {"hk", "🇭🇰"}, {"hu", "🇭🇺"}, {"ie", "🇮🇪"}, {"il", "🇮🇱"},
    {"in", "🇮🇳"}, {"is", "🇮🇸"}, {"it", "🇮🇹"}, {"jp", "🇯🇵"}, {"kr", "🇰🇷"},
    {"lt", "🇱🇹"}, {"lv", "🇱🇻"}, {"md", "🇲🇩"}, {"nl", "🇳🇱"}, {"no", "🇳🇴"},
    {"nz", "🇳🇿"}, {"pl", "🇵🇱"}, {"pt", "🇵🇹"}, {"ro", "🇷🇴"}, {"rs", "🇷🇸"},
    {"ru", "🇷🇺"}, {"se", "🇸🇪"}, {"sg", "🇸🇬"}, {"sk", "🇸🇰"}, {"tr", "🇹🇷"},
    {"tw", "🇹🇼"}, {"ua", "🇺🇦"}, {"us", "🇺🇸"}, {"uk", "🇬🇧"}, {"kz", "🇰🇿"}
};

static const std::unordered_map<std::string, std::string> CITY_FLAGS = {
    {"amsterdam", "🇳🇱"}, {"athens", "🇬🇷"}, {"auckland", "🇳🇿"}, {"bangkok", "🇹🇭"},
    {"barcelona", "🇪🇸"}, {"berlin", "🇩🇪"}, {"brussels", "🇧🇪"}, {"budapest", "🇭🇺"},
    {"chicago", "🇺🇸"}, {"dallas", "🇺🇸"}, {"dubai", "🇦🇪"}, {"dublin", "🇮🇪"},
    {"frankfurt", "🇩🇪"}, {"helsinki", "🇫🇮"}, {"hong kong", "🇭🇰"}, {"istanbul", "🇹🇭"},
    {"kyiv", "🇺🇦"}, {"london", "🇬🇧"}, {"los angeles", "🇺🇸"}, {"madrid", "🇪🇸"},
    {"miami", "🇺🇸"}, {"milan", "🇮🇹"}, {"montreal", "🇨🇦"}, {"moscow", "🇷🇺"},
    {"new york", "🇺🇸"}, {"oslo", "🇳🇴"}, {"paris", "🇫🇷"}, {"prague", "🇨🇿"},
    {"riga", "🇱🇻"}, {"rome", "🇮🇹"}, {"seattle", "🇺🇸"}, {"seoul", "🇰🇷"},
    {"singapore", "🇸🇬"}, {"sofia", "🇧🇬"}, {"stockholm", "🇸🇪"}, {"tallinn", "🇪🇪"},
    {"tokyo", "🇯🇵"}, {"toronto", "🇨🇦"}, {"vienna", "🇦🇹"}, {"vilnius", "🇱🇹"},
    {"warsaw", "🇵🇱"}, {"zurich", "🇨🇭"}
};

std::string flag_for(const std::string& name, const std::string& address) {
    // Check if name already has flag emoji (Unicode Regional Indicator symbols U+1F1E6 to U+1F1FF)
    for (size_t i = 0; i + 3 < name.size(); ++i) {
        unsigned char c1 = name[i];
        unsigned char c2 = name[i+1];
        unsigned char c3 = name[i+2];
        unsigned char c4 = name[i+3];
        if (c1 == 0xF0 && c2 == 0x9F && c3 == 0x87) {
            // Found a regional indicator, likely a flag
            return name.substr(i, 8 < name.size() - i ? 8 : name.size() - i);
        }
    }

    std::string lower_name = name;
    std::transform(lower_name.begin(), lower_name.end(), lower_name.begin(), [](unsigned char c){ return std::tolower(c); });

    // Check cities
    for (const auto& [city, flag] : CITY_FLAGS) {
        if (lower_name.find(city) != std::string::npos) {
            return flag;
        }
    }

    // Check 2-letter country codes
    for (const auto& [code, flag] : CODE_FLAGS) {
        // Look for word boundaries or brackets like [US], -US-, US 1, etc.
        std::string upper_code = code;
        std::transform(upper_code.begin(), upper_code.end(), upper_code.begin(), [](unsigned char c){ return std::toupper(c); });

        size_t pos = name.find(upper_code);
        if (pos != std::string::npos) {
            bool left_ok = (pos == 0 || !std::isalpha(static_cast<unsigned char>(name[pos - 1])));
            bool right_ok = (pos + upper_code.size() >= name.size() || !std::isalpha(static_cast<unsigned char>(name[pos + upper_code.size()])));
            if (left_ok && right_ok) {
                return flag;
            }
        }
    }

    // Check address TLD
    if (!address.empty()) {
        size_t dot = address.rfind('.');
        if (dot != std::string::npos && dot + 1 < address.size()) {
            std::string tld = address.substr(dot + 1);
            std::transform(tld.begin(), tld.end(), tld.begin(), [](unsigned char c){ return std::tolower(c); });
            auto it = CODE_FLAGS.find(tld);
            if (it != CODE_FLAGS.end()) {
                return it->second;
            }
        }
    }

    return "🌐";
}

} // namespace dma2ray::flags
