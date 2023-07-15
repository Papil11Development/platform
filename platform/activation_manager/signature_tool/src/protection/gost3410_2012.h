#include <string>

struct KeyPair
{
    std::string public_key;
    std::string private_key;
};

class GOST3410_2012
{
public:
    std::string sign_message(const std::string& message, const std::string& private_key);
    bool check_sign(const std::string& message, const std::string& sign, const std::string& public_key );
    KeyPair generate_key_pair();
};