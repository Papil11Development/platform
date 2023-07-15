#ifndef __HardwareKey_h_18e972a386994da890377dd2185ad048_
#define __HardwareKey_h_18e972a386994da890377dd2185ad048_

#include <string>
#include <vector>
#include <stdexcept>
#include <random>

namespace tdv {
namespace hkey {

// methods marked with `key exe api` require
//  - key exe installed in the key,
//  - valid UsrPIN,
//  - and initialised access token - except initAccessToken

// data files inside key are stored with meta data:
//  - file size (suddenly)
//  - checksum
// checksum is checked in read methods
// file size is stored because there is no way to change file size after creation
//   so in order to support rewriting file with smaller ammout of bytes
//   we need to store actual file size in it

class HardwareKey
{
public:

	typedef unsigned char UsrPIN[8];
	typedef unsigned char DevPIN[24];

	struct Params
	{
		UsrPIN usr_pin;  // used always
		DevPIN dev_pin;  // used only for reset
	};


	static
	std::string printKeysList();

	// open one key, only one key must be connected
	HardwareKey(const Params params);

	// open key with equal id (many can be connected, but exactly one with equal id)
	//   id must be serial, i.e. 16 bytes string, in hex representing 8 bytes serial
	HardwareKey(const Params params, const std::string id);

	~HardwareKey();

	void setWinkLED(const unsigned char wink_frequency) const;

	void setHIDmode() const;
	void setUSBmode() const;

	// serial is 8 bytes, here it is returned in hex as a string (i.e. 16 bytes string)
	std::string getSerial() const;

	// root dir must have default dev pin ("123456781234567812345678")
	//   after reset root dir will have default dev and user pin
	void resetKey(const std::string exe_file_data);

	// key exe api
	std::string readStaticData();

	// key exe api
	void writeStaticData(const std::string data);

	// key exe api
	std::string readStateData();

	// key exe api
	// you can write only after you read state once
	void writeStateData(const std::string data);

	// key exe api
	// test that key is (still) connected
	void testHealth();

	// key exe api
	void initAccessToken();

private:


	class DESKeyScheduleBuffer { uint64_t d[16]; };
	static_assert(sizeof(DESKeyScheduleBuffer) == 128, "wrong DESKeyScheduleBuffer size");

	static
	DESKeyScheduleBuffer makeDESKey(const int i);

	// encrypt (inplace) with Triple DES with triple-length key
	//   in CBC (Cipher Block Chaining) mode without initialization vector
	// data is a pointer to data_n blocks of 8 bytes (must be aligned)
	static
	void encrypt_3TDES_CBC(
		const DESKeyScheduleBuffer &key1,
		const DESKeyScheduleBuffer &key2,
		const DESKeyScheduleBuffer &key3,
		uint64_t* const data_begin,
		uint64_t* const data_end);

	// same as encrypt_2TDES_CBC but decrypt
	static
	void decrypt_3TDES_CBC(
		const DESKeyScheduleBuffer &key1,
		const DESKeyScheduleBuffer &key2,
		const DESKeyScheduleBuffer &key3,
		uint64_t* const data_begin,
		uint64_t* const data_end);

	template<int n>
	void encryptCommand(uint64_t (&data)[n]) const;

	template<int n>
	void decryptResponse(
		uint64_t (&data)[n],
		const int bytes_count = n * sizeof(uint64_t)) const;


	void open() const;

	void close() const;

	void verifyPin(const UsrPIN &usr_pin) const;

	void verifyPin(const DevPIN &dev_pin) const;

	// need dev permissions
	void writeNewFile(
		const std::string filepath,
		const uint16_t file_id,
		const bool exe_file) const;

	// key exe api
	std::string readKeyFile(const uint16_t &file_id);

	// key exe api
	void writeKeyFile(const uint16_t &file_id, const std::string &pure_data);

	// key exe api
	void copyKeyFile(
		const uint16_t &src_file_id,
		const uint16_t &dst_file_id);

	// key exe api
	void testBadCommand();


	uint32_t getKeyFileSize(
		const uint16_t &file_id);


	void writeAccessToken4bytes(unsigned char* const dst) const;
	void readAccessToken4bytes(unsigned char const* const src);

	void resetRandomSeed();

	uint64_t random64bit();


	// add 18 bytes to the left
	//  2 bytes - file size
	//  16 bytes - checksum
	static std::string prepareFileData(const std::string &pure_data);

	// check checksum, and remove first 18 bytes of meta data
	static std::string getPureData(const std::string &file_data);

	// store SENSE4_CONTEXT as a vector<char>
	//   so we don't need to include sense4.h
	const std::vector<char> context;

	const Params params;

	unsigned char access_token[4];



	// commands will be encrypted with key A
	// results from the key will be encrypted with key B
	const DESKeyScheduleBuffer key1_A;
	const DESKeyScheduleBuffer key2_A;

	const DESKeyScheduleBuffer key1_B;
	const DESKeyScheduleBuffer key2_B;

	std::mt19937_64 random_engine;

	bool main_state_file_good = false;

	HardwareKey(const HardwareKey&) = delete;
	HardwareKey(const HardwareKey&&) = delete;
	HardwareKey& operator=(const HardwareKey&) = delete;
	HardwareKey& operator=(const HardwareKey&&) = delete;
};


// exceptions will be of this type
class Error : public std::exception
{
public:

	virtual ~Error() throw() { }

	Error(
		unsigned int code,
		unsigned int code2)
	: _code(code) { addCode(code); addCode(code2); }

	Error(
		unsigned int code,
		std::string what) : _code(code), _what(what) { }

	virtual const char* what() const throw() { return _what.c_str(); }

	unsigned int code() const throw() { return _code; }

	void addCode(unsigned int code);

private:

	unsigned int _code;
	std::string _what;
};


}  // hkey namespace
}  // tdv namespace


#endif  // __HardwareKey_h_18e972a386994da890377dd2185ad048_