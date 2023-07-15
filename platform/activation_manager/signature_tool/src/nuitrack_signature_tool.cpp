//#include "protection/license_base.h"
#include "protection/gost3410_2012.h"
//#include "hds/libhds.h"

#include <stdio.h>
#include <iostream>
#include <fstream>
#include <boost/program_options.hpp>
#include <boost/algorithm/string.hpp>
#include <boost/property_tree/ptree.hpp>
#include <boost/property_tree/json_parser.hpp>

using namespace std;
using namespace boost::program_options;
using namespace boost::property_tree;

// public nuitrack key
std::string pbk("");

string exec(const char* cmd)
{
	FILE* pipe = popen(cmd, "r");
	if (!pipe)
		return "ERROR";

	char buffer[128];
	std::string result = "";
	while(!feof(pipe))
	{
		if(fgets(buffer, sizeof(buffer), pipe) != NULL)
			result += buffer;
	}
	pclose(pipe);
	boost::algorithm::trim(result);

	return result;
}

string getAndroidSignature(string signatureGenerator)
{
	return "";
}

string getLinuxSignature()
{
	return "";
}

int main(int argc, char** argv)
{
	options_description desc("Usage: [-p path_to_signature_generator] [-s device_signature] -k key -n license_file");

	desc.add_options()
	        ("help,h", "help message")
	        ("signature-generator,p", value<string>(), "set path to android device signature generator "
	                                                   "(likely build_android/bin/nuitrack_signature_genetator)")
	        ("signature,s", value<string>(), "device signature")
	        ("private-key,k", value<string>(), "set path to private key file (likely nuitrack_private.key)")
	        ("license-file,n", value<string>(), "set path to license file")
	        ("verify,v", "verify certificate")
	        ("certificate,c", value<string>(), "verifying certificate")
	        ("public-key", value<string>(), "set path to public key file");

	variables_map vm;
	store(command_line_parser(argc, argv).options(desc).run(), vm);
	notify(vm);
	
	if (vm.count("public-key") == 1)
	{
		string publicKeyFile = vm["public-key"].as<string>();
		ifstream publicKeyStream(publicKeyFile.c_str());
		if (!publicKeyStream.is_open())
		{
			cerr << "Can't read public key file" << endl;
			return EXIT_FAILURE;
		}
	
		string publicKey;
		publicKeyStream >> publicKey;
		pbk = publicKey;
	}
	
	if (vm.count("verify") > 0)
	{
		if (vm.count("signature") != 1)
		{
			cerr << desc << endl;
			cerr << "Specify signature" << endl;
			return EXIT_FAILURE;
		}
		if (vm.count("certificate") != 1)
		{
			cerr << desc << endl;
			cerr << "Specify certificate" << endl;
			return EXIT_FAILURE;
		}
		if (vm.count("public-key") != 1)
		{
			cerr << desc << endl;
			cerr << "Specify public key file" << endl;
			return EXIT_FAILURE;
		}
		
		bool matched = GOST3410_2012().check_sign(vm["signature"].as<string>(),
		        vm["certificate"].as<string>(), pbk);
		
		cerr << "Verify certificate: " << (matched ? "OK" : "failed");
		
		return (matched ? EXIT_SUCCESS : EXIT_FAILURE);
	}

	// ----------------- get device signature
	string deviceSignature;
	if (vm.count("signature") == 1)
	{
		deviceSignature = vm["signature"].as<string>();
	}
	else if (vm.count("signature-generator") == 1)
	{
		cerr << "Getting android device signature..." << endl;
		string signatureGenerator = vm["signature-generator"].as<string>();
		deviceSignature = getAndroidSignature(signatureGenerator);
	}
	else
	{
		cerr << "Signature generator not specified, getting linux device signature..." << endl;
		deviceSignature = getLinuxSignature();
	}
	cerr << "Device signature: " << deviceSignature << endl;

	if (vm.count("help") || /*vm.count("signature-generator") != 1 ||*/
			vm.count("private-key") != 1 || vm.count("license-file") != 1)
	{
		cerr << desc << endl;
		return EXIT_FAILURE;
	}

	// ----------------- get private key
	string privateKeyFile = vm["private-key"].as<string>();
	ifstream privateKeyStream(privateKeyFile.c_str());
	if (!privateKeyStream.is_open())
	{
		cerr << "Can't read private key file" << endl;
		return EXIT_FAILURE;
	}

	string privateKey;
	privateKeyStream >> privateKey;

	// ---------------- signing device signature
	GOST3410_2012 signer;
	string certificate = signer.sign_message(deviceSignature, privateKey);
	cerr << "Certificate = " << certificate << endl;
	
	// ---------------- checking certificate
	cerr << "Verify certificate: " << (signer.check_sign(deviceSignature, certificate, pbk)
								 ? "OK" : "failed") << endl;

	// ---------------- save certificate in license file
	string licenseFile = vm["license-file"].as<string>();

	ptree pt;
	try
	{
		json_parser::read_json(licenseFile, pt);
	}
	// rewriting if cannot read license file (not exist or not consistent)
	catch (...)
	{
		cerr << "Error reading license file " + licenseFile << endl;
		cerr << "Rewriting it..." << endl;
		pt.clear();
	}
	try
	{
		pt.put("NuitrackLicense", certificate);
		json_parser::write_json(licenseFile, pt);
	}
	catch (...)
	{
		cerr << "Cannot write license to " + licenseFile << endl;
		cerr << "Certificate saving status: Failed" << endl;
		exit(EXIT_FAILURE);
	}

	cerr << "Certificate saving status: OK" << endl;
	return EXIT_SUCCESS;
}
