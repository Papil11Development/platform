cmake_minimum_required (VERSION 2.8) 

set(PROJECT_NAME api_senselock)
project(${PROJECT_NAME})

add_definitions(-std=c++11)
add_definitions(-fPIC)

find_package(PythonLibs)

include_directories(
	${CMAKE_CURRENT_SOURCE_DIR}/include
	${CMAKE_CURRENT_SOURCE_DIR}/include/tdv_hardware_key
	${CMAKE_CURRENT_SOURCE_DIR}/../native/include
	${CMAKE_CURRENT_SOURCE_DIR}/../build/install/3rdparty/include
	${CMAKE_CURRENT_SOURCE_DIR}/../build/install/3rdparty/include/boost/python
	${PYTHON_INCLUDE_DIRS}
)

link_directories(
	${CMAKE_CURRENT_SOURCE_DIR}/../build/install/3rdparty/lib
        ${CMAKE_CURRENT_SOURCE_DIR}/../build
	${CMAKE_CURRENT_SOURCE_DIR}/lib
	${PYTHON_LIBRARY_DIRS}
)

set(LIBS
	hwkey
	sense4
	opencv_core
	usb
	crypto
	boost_numpy34
	boost_python34
	boost_filesystem
	boost_system
	python_cpp_bridge
)

set(SOURCES
	${CMAKE_CURRENT_SOURCE_DIR}/src/ApiSenselock.cpp
)

add_library(${PROJECT_NAME} SHARED ${SOURCES})

target_compile_definitions(${PROJECT_NAME} PRIVATE -DPYTHON_PACKAGE_NAME=${PROJECT_NAME})

set_target_properties(${PROJECT_NAME} PROPERTIES PREFIX "")
target_link_libraries(${PROJECT_NAME} ${LIBS})
