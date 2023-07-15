#include "ApiSenselock.h"
#include "PythonModuleRegistrator.h"
#include "PythonModuleExpose.h"
#include <iostream>
#include <vector>

using namespace python_cpp_bridge;
namespace pt = boost::property_tree;


template <typename T>
std::vector<T> extractVect(pt::ptree const& pt, pt::ptree::key_type const& key) {	
	std::vector<T> r;
	for (auto& item : pt.get_child(key))
		r.push_back(item.second.get_value<T>());
	return r;
}

pyHardwareKey::pyHardwareKey(const NativeParams& params) {
	tdv::hkey::HardwareKey::Params p;
	std::string id;

	try {
		std::vector<unsigned char> vectUsrPin = extractVect<unsigned char>(params.sparseData, "usr_pin");
		for (int i = 0; i < sizeof(tdv::hkey::HardwareKey::UsrPIN); ++i)
			p.usr_pin[i] = vectUsrPin[i];
	} catch(...) {
		std::cout << "WARNING: usr_pin not found\n";
	}

	try {
		std::vector<unsigned char> vectDevPin = extractVect<unsigned char>(params.sparseData, "dev_pin");
		for (int i = 0; i < sizeof(tdv::hkey::HardwareKey::DevPIN); ++i)
			p.dev_pin[i] = vectDevPin[i];	
	} catch(...) {
		std::cout << "WARNING: dev_pin not found\n";
	}

	try {
		id = params.sparseData.get<std::string>("id");
		hardwareKey = new tdv::hkey::HardwareKey(p, id);
	} catch(...) {
		hardwareKey = new tdv::hkey::HardwareKey(p);	
	}
	
	hardwareKey->initAccessToken();
}

std::string pyHardwareKey::type() {
	return "pyHardwareKey";
}

NativeParams pyHardwareKey::readStaticData() {
	NativeParams result;
	std::string data = hardwareKey->readStaticData();

	result.sparseData.put("data", data);
	return result;
}

NativeParams pyHardwareKey::readStateData() {
	NativeParams result;
	std::string data = hardwareKey->readStateData();

	result.sparseData.put("data", data);
	return result;
}

void pyHardwareKey::writeStateData(const NativeParams& data) {
	std::string d = data.sparseData.get<std::string>("data");	
	hardwareKey->writeStateData(d);
}

python_cpp_bridge::NativeParams pyHardwareKey::process(python_cpp_bridge::NativeParams& data) {
	std::string strFunc;
	try {
		strFunc = data.sparseData.get<std::string>("call");	
	} catch(...) {
		std::cout << "Call function: {\"call\": func}\n";
		std::cout << "Available functions:\n\treadStaticData,\n\treadStateData,\n\t";
		std::cout << "writeStateData:\n\t\tparam (dict): {\"data\": state_data}\n";
	}
	

	if (strFunc.compare("readStaticData") == 0)
		return this->readStaticData();
	else if (strFunc.compare("readStateData") == 0)
		return this->readStateData();
	else if (strFunc.compare("writeStateData") == 0)
		this->writeStateData(data);

	NativeParams result;
	return result;
}


static PythonModuleRegistrator<pyHardwareKey> registrator;
