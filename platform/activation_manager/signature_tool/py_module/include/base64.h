#ifndef __BASE_64_ENCODE_H_
#define __BASE_64_ENCODE_H_

#include <string>

std::string base64_encode(unsigned char const* , unsigned int len);
std::string base64_decode(std::string const& s);

#endif  // __BASE_64_ENCODE_H_