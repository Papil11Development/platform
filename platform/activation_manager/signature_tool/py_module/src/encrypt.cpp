#include "encrypt.h"

#include <sstream>
#include <cstring>
// #include <iostream>
#include <stdexcept>


void convert_string_to_des_keys(const std::string keys_str, const_DES_cblock keys[4])
{
	const char* keys_ptr = &keys_str[0];

	const int keys_count = 4; // 3 keys with init vector
	const int key_size = 8;
	for (int k = 0; k < keys_count; ++k)
	{
		unsigned char* const key = &keys[k][0];
		for (int i = 0; i < key_size; ++i)
		{
			char buf[3];
			buf[0] = *keys_ptr++;
			buf[1] = *keys_ptr++;
			buf[2] = '\0';

			int value = 0;
			sscanf(buf, "%x", &value);
			key[i] = (unsigned char)value;
		}

		// for (int i = 0; i < key_size; ++i)
		// {
		// 	printf("%02X ", key[i]);
		// }
		// printf("\n");
	}
}

std::string encrypt(
	const_DES_cblock keys[4],
	const std::string input,
	const bool is_encrypt)
{
	int len = input.length();
	std::string input_string;

	if (is_encrypt)
	{
		std::stringstream sst;
		int64_t size = input.length();
		sst.write((const char*)&size, sizeof(int64_t));
		sst.write(input.data(), input.length());
		sst.flush();

		input_string.resize(sizeof(int64_t) + size);

		sst.read((char*)input_string.data(), input_string.length());

		len = input_string.length();
		input_string.resize((len + 7) / 8 * 8, (unsigned char)(8 - (len & 7)));
		len = input_string.length();
	}
	else
	{
		if (len % 8)
			throw std::runtime_error("Input error: encrypt input size is " +
				std::to_string(len) + " bytes, but must be a multiple of 8 bytes");
	}

	/* Init vector */
	DES_cblock iv1;
	memcpy(iv1, keys[3], sizeof(DES_cblock));

	DES_key_schedule SchKey1, SchKey2, SchKey3;
	DES_set_key(&keys[0], &SchKey1);
	DES_set_key(&keys[1], &SchKey2);
	DES_set_key(&keys[2], &SchKey3);

	/* Buffers for Encryption and Decryption */
	std::string encrypted;
	std::string decrypted;
	encrypted.resize(len);
	decrypted.resize(len);

	/* Triple-DES CBC Encryption */
	if (is_encrypt)
		DES_ede3_cbc_encrypt( (unsigned char*)input_string.data(), (unsigned char*)encrypted.data(), len, &SchKey1, &SchKey2, &SchKey3, &iv1, DES_ENCRYPT);
	else
		encrypted = input;

	/* Triple-DES CBC Decryption */
	DES_cblock iv2; // You need to start with the same iv value
	memcpy(iv2, keys[3], sizeof(DES_cblock));
	DES_ede3_cbc_encrypt( (unsigned char*)encrypted.data(), (unsigned char*)decrypted.data(), len, &SchKey1, &SchKey2, &SchKey3, &iv2, DES_DECRYPT);

	if (is_encrypt && input_string != decrypted)
		throw std::runtime_error("OpenSSL error: decrypted data differ from original data");

	return is_encrypt ? encrypted : decrypted;
}
