#include <boost/multiprecision/cpp_int.hpp>
#include <ostream>

typedef boost::multiprecision::cpp_int b_int; 

void extended_euclid(b_int a, b_int b, b_int *x, b_int *y, b_int *d);
b_int inverse(b_int& a, b_int& n);
b_int modul(const b_int& src, const b_int& m);

class ECurvePoint {
public:
    ECurvePoint(const b_int &_x, const b_int &_y, const b_int &_a, const b_int &_p, bool _is_O);
    ECurvePoint(const ECurvePoint& cp);
    ECurvePoint& operator+=(const ECurvePoint& rhs);
    ECurvePoint& operator*=(const b_int& k);
    bool operator==(const ECurvePoint& rhs);

    const b_int& get_x();
    const b_int& get_y();
    const b_int& get_p();
    bool is_zero();

    friend std::ostream& operator<<(std::ostream& o, const ECurvePoint& pt);
private:
    b_int x;
    b_int y;
    b_int p;
    b_int a;
    bool is_O;
};

inline ECurvePoint operator+(ECurvePoint lhs, const ECurvePoint& rhs)
{
  lhs += rhs;
  return lhs;
}

inline ECurvePoint operator*(ECurvePoint lhs, const b_int& k)
{
  lhs *= k;
  return lhs;
}