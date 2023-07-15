cmake_minimum_required (VERSION 2.8) 

set(PROJECT_NAME api_signature_tool)
project(${PROJECT_NAME})


add_definitions(-std=c++11)
add_definitions(-fPIC)

set(WORKSPACE ${CMAKE_CURRENT_SOURCE_DIR}/../../../../)
message("-- Workspace directory: ${WORKSPACE}")

find_package(PythonLibs)

include_directories(
	${CMAKE_CURRENT_SOURCE_DIR}/include
    ${CMAKE_CURRENT_SOURCE_DIR}/../src
	${WORKSPACE}/python-cpp-bridge/native/include
	${WORKSPACE}/python-cpp-bridge/build/install/3rdparty/include
    ${WORKSPACE}/python-cpp-bridge/build/install/3rdparty/include/boost/python
    ${WORKSPACE}/openssl/openssl-ubuntu14.04-x86-64-install-dir/include
    ${WORKSPACE}/gemalto-rms/development/c/include
	${PYTHON_INCLUDE_DIRS}
)

link_directories(
	${WORKSPACE}/python-cpp-bridge/build/install/3rdparty/lib
    ${WORKSPACE}/python-cpp-bridge/build
    ${WORKSPACE}/gemalto-rms/development/c/lib/x86_64/static
    ./opencv
    ${PYTHON_LIBRARY_DIRS}
    ${WORKSPACE}/openssl/openssl-ubuntu14.04-x86-64-install-dir/lib
)

set(LIBS
    crypto
    ssl
	opencv_core
	boost_numpy34
	boost_python34
	boost_filesystem
	boost_system
	python_cpp_bridge
    lssrv64
    dl
)

set(SOURCES
	${CMAKE_CURRENT_SOURCE_DIR}/src/api_signature_tool.cpp
    ${CMAKE_CURRENT_SOURCE_DIR}/../src/gost3410_2012.cpp
    ${CMAKE_CURRENT_SOURCE_DIR}/../src/gost28147_1989.cpp
    ${CMAKE_CURRENT_SOURCE_DIR}/../src/gosthash.cpp
    ${CMAKE_CURRENT_SOURCE_DIR}/../src/gost.cpp
    ${CMAKE_CURRENT_SOURCE_DIR}/../src/gost_cbc.cpp
    ${CMAKE_CURRENT_SOURCE_DIR}/../src/ecurve_point.cpp
    ${CMAKE_CURRENT_SOURCE_DIR}/src/base64.cpp
    ${CMAKE_CURRENT_SOURCE_DIR}/src/encrypt.cpp
)

add_library(${PROJECT_NAME} SHARED ${SOURCES})

target_compile_definitions(${PROJECT_NAME} PRIVATE -DPYTHON_PACKAGE_NAME=${PROJECT_NAME})

set_target_properties(${PROJECT_NAME} PROPERTIES PREFIX "")
target_link_libraries(${PROJECT_NAME} ${LIBS})
