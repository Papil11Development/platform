#ifndef __API_SIGNATURE_TOOL_H_
#define __API_SIGNATURE_TOOL_H_

#include "NativeParams.h"
#include "encrypt.h"

class pySignatureTool {
public:
    pySignatureTool(const python_cpp_bridge::NativeParams& params);
    python_cpp_bridge::NativeParams process(python_cpp_bridge::NativeParams& sample);
    static std::string type();
private:
    std::string publicKey;
    std::string signature;
    std::string certificate;
    std::string privateKey;
    std::string licenseFile;
    DES_cblock _keys[4];
};

#endif  // __API_SIGNATURE_TOOL_H_