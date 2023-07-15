#include "protection/ecurve_point.h"

using boost::multiprecision::cpp_int;
void extended_euclid(b_int a, b_int b, b_int *x, b_int *y, b_int *d)
{
    b_int q, r, x1, x2, y1, y2;
    if (b == 0) {
        *d = a, *x = 1, *y = 0;
        return;
    }

    x2 = 1, x1 = 0, y2 = 0, y1 = 1;
    while (b > 0) {
        q = a / b, r = a - q * b;
        *x = x2 - q * x1, *y = y2 - q * y1;
        a = b, b = r;
        x2 = x1, x1 = *x, y2 = y1, y1 = *y;
    }

    *d = a, *x = x2, *y = y2;
}

b_int inverse(b_int& a, b_int& n)
{
    b_int d, x, y;
    extended_euclid(a, n, &x, &y, &d);
    if (d == 1) return x;
    return 0;
}

b_int modul(const b_int& src, const b_int& m)
{
    if(src < 0){ 
        return ( src + m - (m * ( (b_int)( src / m) )) ) % m;
    }
    return src % m;
}

ECurvePoint::ECurvePoint(const b_int &_x, const b_int &_y, const b_int &_a, const b_int &_p, bool _is_O)
{
    x = _x; y = _y; p = _p; is_O = _is_O; a = _a;
}

ECurvePoint::ECurvePoint(const ECurvePoint& pt2)
{
    x = pt2.x; y = pt2.y; p = pt2.p; is_O = pt2.is_O ; a = pt2.a;
}

bool ECurvePoint::operator==(const ECurvePoint& pt)
{
    return pt.x == x && pt.y == y && pt.p == p && pt.is_O == is_O && a == pt.a;
}

const b_int& ECurvePoint::get_x()
{
    return x;
}
const b_int& ECurvePoint::get_y()
{
    return y;
}
const b_int& ECurvePoint::get_p()
{
    return p;
}
bool ECurvePoint::is_zero()
{
    return is_O;
}

std::ostream& operator<<(std::ostream& o, const ECurvePoint& pt)
{
    o << "x = " << pt.x << std::endl;
    o << "y = " << pt.y << std::endl;
    o << "p = " << pt.p << std::endl;
    o << "a = " << pt.a << std::endl;
    o << "is O? = " << pt.is_O << std::endl;
    return o;
}

ECurvePoint& ECurvePoint::operator+=(const ECurvePoint& pt2)
{
    if( pt2.is_O )
    {
        return *this;
    }
    if( is_O ) 
    {
        *this = pt2;
        return *this;
    }

    if( y == -pt2.y )
    {
        is_O = true;
        return *this;
    } 

    b_int x_tmp = x;
    b_int lambda;

    if( x != pt2.x ) {
        b_int lambda_denumerator = modul(pt2.x - x, p);
        b_int lambda_numerator = modul(pt2.y - y, p);
        b_int inverse_lambda_denumerator = modul(inverse( lambda_denumerator, p ),p);
        lambda = modul((lambda_numerator * inverse_lambda_denumerator ), p);
        b_int lambda_2 = modul(lambda * lambda, p);
        x = modul( lambda_2 - x - pt2.x, p );
    } else {
        b_int lambda_denumerator = modul(2 * y, p);
        b_int lambda_numerator = modul(3 * x * x + a, p);

        b_int inverse_lambda_denumerator = modul(inverse( lambda_denumerator, p ),p);

        lambda = modul((lambda_numerator * inverse_lambda_denumerator ), p);
        b_int lambda_2 = modul(lambda * lambda, p);

        x = modul( lambda_2 - 2 * x , p);
    }

    y = modul(lambda * ( x_tmp - x ) - y, p);
    return *this;
}

ECurvePoint& ECurvePoint::operator*=(const b_int& k)
{
    ECurvePoint result(0,0,a,p,true);
    b_int n = k;
    ECurvePoint point = *this;
    while( n > 0 )
    {
        if( n & 1 )
        {
            result += point;
        }
        point += point;
        n = n >> 1;
    }
    *this = result;
    return *this;
}
