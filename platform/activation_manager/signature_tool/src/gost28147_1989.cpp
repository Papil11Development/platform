#include "protection/gost28147_1989.h"

#include "protection/gost.h"
#include "protection/gosthash.h"

#include <sstream>
#include <iomanip> 

std::string GOSTCalc::hash(const std::string& message)
{
    GOSTHASH_CTX ctx;
    unsigned char digest[GOST_HASH_BYTES_SZ];
    std::stringstream ss;
    
    GOSThash_Init( &ctx );
    GOSThash_Update( &ctx, (const void *)message.c_str(), message.size());
    GOSThash_Final( &ctx, digest );

    ss << std::hex << std::setfill('0');
    for( int i = 0; i < GOST_HASH_BYTES_SZ; i++)
    {
        ss << std::setw(2) << std::uppercase << static_cast<unsigned>(digest[i]);
    } 
    std::string result = ss.str();
    return result;
}
