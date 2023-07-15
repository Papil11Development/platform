#ifndef __API_SENSELOCK_H_
#define __API_SENSELOCK_H_

#include "HardwareKey.h"
#include "NativeParams.h"
#include <string>


class pyHardwareKey {
public:
	pyHardwareKey(const python_cpp_bridge::NativeParams& params);

	static std::string type();

	python_cpp_bridge::NativeParams readStaticData();

	python_cpp_bridge::NativeParams readStateData();

	void writeStateData(const python_cpp_bridge::NativeParams& data);

	python_cpp_bridge::NativeParams process(python_cpp_bridge::NativeParams& sample);

private:
	tdv::hkey::HardwareKey* hardwareKey;
};


#endif  // __API_SENSELOCK_H_
