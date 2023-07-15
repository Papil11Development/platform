#ifndef ENCRYPT_H_
#define ENCRYPT_H_

#include <openssl/des.h>
#include <string>


void convert_string_to_des_keys(
	const std::string keys_str,
	const_DES_cblock keys[4]);

std::string encrypt(
	const_DES_cblock keys[4],
	const std::string input,
	const bool is_encrypt=true);

#endif // ENCRYPT_H_
