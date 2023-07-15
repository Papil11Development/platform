#include "api_signature_tool.h"
#include "PythonModuleRegistrator.h"
#include "PythonModuleExpose.h"
#include "protection/gost3410_2012.h"
#include "base64.h"
#include "key.h"
#include <iostream>
#include <string>
#include <string.h>
#include "licensing.h"
#include <boost/property_tree/xml_parser.hpp>

using namespace python_cpp_bridge;
namespace pt = boost::property_tree;

void description() {
    std::cerr << "RMS API: Unable to get information about Feature.\n";
}

pySignatureTool::pySignatureTool(const NativeParams& params)
{
    convert_string_to_des_keys(get_secret_key_and_iv(), _keys);
}

NativeParams pySignatureTool::process(NativeParams& params) {
    NativeParams result;

    pt::ptree payload = params.sparseData.get_child("payload");
    std::string salt = params.sparseData.get<std::string>("salt");
    std::string callFunc = payload.get<std::string>("call", "");

    if (callFunc.compare("FeatureInfo") == 0) {
        std::string fieldName = payload.get<std::string>("field", "");
        std::string contact_server = payload.get<std::string>("server", "");
        std::string Scope = "<?xml version=\"1.0\" encoding=\"UTF-8\"?>"
                                "<sentinelScope>"
                                    "<feature index=\"0\">"
                                    "<name>"+payload.get<std::string>("feature", "")+"</name>"
                                    "<version>"+payload.get<std::string>("version", "")+"</version>"
                                    "</feature>"
                                "</sentinelScope>";
        char *pcFeatureInfo = NULL;
        int  iRetCode;
        sntl_licensing_attr_t *pAttrAppContext = NULL;
        sntl_licensing_app_context_t *pAppContext = NULL;
        sntl_licensing_login_session_t *pLogin = NULL;

        std::stringstream sst;

        iRetCode = sntl_licensing_attr_new(&pAttrAppContext);
        if(!iRetCode)
            iRetCode = sntl_licensing_attr_set_appcontext_contact_server (pAttrAppContext, contact_server.c_str());
        if(!iRetCode)
            iRetCode = sntl_licensing_app_context_new(0, pAttrAppContext, &pAppContext);
        if(!iRetCode)
            iRetCode = sntl_licensing_get_info(pAppContext, Scope.c_str(), SNTL_QUERY_FEATURE_INFO_VERSION("1.0"), &pcFeatureInfo);
        if(!iRetCode)
            iRetCode = sntl_licensing_login(pAppContext, payload.get<std::string>("feature", "").c_str(), &pLogin);
        if(!iRetCode)
            iRetCode = sntl_licensing_logout(pLogin);
	    if(iRetCode)
            sst << "{\"status\":\"error\", \"code\":\"" << iRetCode << "\", \"salt\":" << salt << "}";
        else{
            pt::ptree feature;
            std::stringstream stream(pcFeatureInfo);
            read_xml(stream, feature);

            sst << "{\"status\":\"ok\", \"salt\":" << salt << ", ";
            sst << "\"" << fieldName << "\":" << feature.get<std::string>("sentinelInfo.feature."+fieldName) << "}";
        }
        sntl_licensing_cleanup();

        const std::string encrypted = encrypt(_keys, sst.str());
        result.sparseData.put("payload", base64_encode((const unsigned char*)encrypted.c_str(), encrypted.length()));
        return result;
    }
    else {
        description();
        exit(EXIT_FAILURE);
    }
}

std::string pySignatureTool::type() {
    return "pySignatureTool";
}

static PythonModuleRegistrator<pySignatureTool> registrator;
