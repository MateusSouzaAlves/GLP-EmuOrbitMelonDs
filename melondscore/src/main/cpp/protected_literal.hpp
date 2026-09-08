#pragma once

#include <array>
#include <cstddef>
#include <cstdint>
#include <cstdio>

#ifndef EMUORBIT_PROTECTED_LITERAL_SEED
#error "Protected literal seed is required"
#endif

namespace emuorbit::protection
{

constexpr std::uint8_t LiteralMask(std::uint32_t domain, std::size_t index) noexcept
{
    std::uint32_t state = static_cast<std::uint32_t>(EMUORBIT_PROTECTED_LITERAL_SEED)
        ^ domain ^ static_cast<std::uint32_t>((index + 1U) * 0x9E3779B9U);
    state ^= state << 13U;
    state ^= state >> 17U;
    state ^= state << 5U;
    state += domain * 0x45D9F3BU + static_cast<std::uint32_t>(index * 0x27D4EB2DU);
    return static_cast<std::uint8_t>(state ^ (state >> 8U) ^ (state >> 16U));
}

template<std::uint32_t Domain, std::size_t Size>
class EncodedLiteral
{
public:
    class Decoded final
    {
    public:
        __attribute__((noinline)) explicit Decoded(
            const std::array<std::uint8_t, Size>& encoded) noexcept
        {
            volatile const std::uint8_t* source = encoded.data();
            for (std::size_t index = 0; index < Size; ++index)
            {
                bytes_[index] = static_cast<char>(
                    source[index] ^ LiteralMask(Domain, index));
            }
        }

        Decoded(const Decoded&) = delete;
        Decoded& operator=(const Decoded&) = delete;

        ~Decoded() noexcept
        {
            volatile char* destination = bytes_.data();
            for (std::size_t index = 0; index < Size; ++index)
                destination[index] = 0;
        }

        const char* c_str() const noexcept
        {
            return bytes_.data();
        }

    private:
        std::array<char, Size> bytes_{};
    };

    constexpr explicit EncodedLiteral(const char (&plain)[Size]) noexcept
        : encoded_{}
    {
        for (std::size_t index = 0; index < Size; ++index)
        {
            encoded_[index] = static_cast<std::uint8_t>(plain[index])
                ^ LiteralMask(Domain, index);
        }
    }

    __attribute__((noinline)) Decoded Decode() const noexcept
    {
        return Decoded(encoded_);
    }

private:
    std::array<std::uint8_t, Size> encoded_;
};

template<std::uint32_t Domain, std::size_t Size>
constexpr EncodedLiteral<Domain, Size> Encode(const char (&plain)[Size]) noexcept
{
    return EncodedLiteral<Domain, Size>(plain);
}

template<typename Encoded, typename... Arguments>
int ProtectedSnprintf(
    char* destination,
    std::size_t capacity,
    const Encoded& encoded,
    Arguments... arguments) noexcept
{
    auto format = encoded.Decode();
    return std::snprintf(destination, capacity, format.c_str(), arguments...);
}

}
