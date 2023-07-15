#ifndef GOST_WRAPPER_H
#define GOST_WRAPPER_H

#include <string>
class GOSTCalc
{
public:
    std::string hash(const std::string& message);
};

#endif