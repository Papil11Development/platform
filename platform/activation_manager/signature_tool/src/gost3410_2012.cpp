#include "protection/gost3410_2012.h"
#include "protection/gost28147_1989.h"
#include "protection/ecurve_point.h"
#include <boost/multiprecision/cpp_int.hpp>
#include <boost/multiprecision/random.hpp>
#include <sstream>
#include <iomanip> 

using namespace boost::multiprecision;
using namespace boost::random;

typedef independent_bits_engine<mt19937, 256, cpp_int> generator_type;

b_int p("57896044618658097711785492504343953926634992332820282019728792003956564821041");
b_int a("7");
b_int b("43308876546767276905765904595650931995942111794451039583252968842033849580414");
b_int m("57896044618658097711785492504343953927082934583725450622380973592137631069619");
b_int q("57896044618658097711785492504343953927082934583725450622380973592137631069619");
b_int x_p("2");
b_int y_p("4018974056539037503335449422937059775635739389905545080690979365213431566280");

std::string b_int_to_hex( const b_int& src )
{
    std::stringstream ss;
    ss << std::hex << std::setfill('0') << std::setw(64) << src;
    return ss.str();
}

std::string GOST3410_2012::sign_message(const std::string& message, const std::string& private_key)
{
    mt19937 base_gen(clock());
    generator_type gen(base_gen);
    b_int k = modul(gen(),q);

    GOSTCalc c;
    std::string message_hash = std::string("0x") + c.hash(message);
    std::string pk = std::string("0x") + private_key;

    b_int e( message_hash );
    e = modul(e,q);
    b_int d( pk );

    ECurvePoint P( x_p, y_p, a, p, false );

    ECurvePoint C = P * k;

    b_int r = modul(C.get_x(),q);
    b_int s = modul((r * d + k * e),q);

    return b_int_to_hex(s) + b_int_to_hex(r);
}

bool GOST3410_2012::check_sign(const std::string& message, const std::string& sign, const std::string& public_key )
{
    GOSTCalc c;
    std::string message_hash = std::string("0x") + c.hash(message);
    std::string s_str = std::string("0x") + sign.substr(0,64);
    std::string r_str = std::string("0x") + sign.substr(64,64);
    std::string x_q_str = std::string("0x") + public_key.substr(0,64);
    std::string y_q_str = std::string("0x") + public_key.substr(64,64);

    b_int e( message_hash );
    b_int s( s_str );
    b_int r( r_str );
    b_int x_q( x_q_str );
    b_int y_q( y_q_str );

    b_int v = modul(inverse( e, q ),q);

    b_int z1 = modul((s * v),q);
    b_int z2 = modul((-r * v ) ,q );

    ECurvePoint P( x_p, y_p, a, p, false );
    ECurvePoint Q( x_q, y_q, a, p, false );
    ECurvePoint nC = (P * z1) + (Q * z2);
    b_int R = modul(nC.get_x(),q);

    if( R == r )
    {
        return true;
    }
    return false;
}

KeyPair GOST3410_2012::generate_key_pair()
{
    KeyPair kp;
    mt19937 base_gen(clock());
    generator_type gen(base_gen);
    b_int d = modul(gen(),q);
    ECurvePoint P( x_p, y_p, a, p, false );
    ECurvePoint Q = P * d;

    kp.private_key = b_int_to_hex(d);
    kp.public_key = b_int_to_hex(Q.get_x()) + b_int_to_hex(Q.get_y()) ;

    return kp;
}
