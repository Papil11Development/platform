
/* 
 * Cryptographic API.
 *
 * Russian hash alg
 *
 * Author: Igor V. Moukatchev <mig@papillon.ru>
 *	
 * Copyright (c) 2005 Papillon Sysytem Ltd.* 
 *
 */
#include <string.h>
#include <stdio.h>
#include <sstream>
#include "protection/gost.h"
#include "protection/gosthash.h"


#define __litle_end__ 
#define __optimized__	

/* ����� ����� ������������ � ��������� ��������������
   � ������� ����   34.11-94  
*/
KBOX GOSThash_example_kbox = {
/* k1 */ { 0x4, 0xa, 0x9 ,0x2,  0xd, 0x8, 0x0, 0xe,  0x6, 0xb, 0x1, 0xc,  0x7, 0xf, 0x5, 0x3 },
/* k2 */ { 0xe, 0xb, 0x4 ,0xc,  0x6, 0xd, 0xf, 0xa,  0x2, 0x3, 0x8, 0x1,  0x0, 0x7, 0x5, 0x9 }, 
/* k3 */ { 0x5, 0x8, 0x1 ,0xd,  0xa, 0x3, 0x4, 0x2,  0xe, 0xf, 0xc, 0x7,  0x6, 0x0, 0x9, 0xb }, 
/* k4 */ { 0x7, 0xd, 0xa ,0x1,  0x0, 0x8, 0x9, 0xf,  0xe, 0x4, 0x6, 0xc,  0xb, 0x2, 0x5, 0x3 }, 
/* k5 */ { 0x6, 0xc, 0x7 ,0x1,  0x5, 0xf, 0xd, 0x8,  0x4, 0xa, 0x9, 0xe,  0x0, 0x3, 0xb, 0x2 }, 
/* k6 */ { 0x4, 0xb, 0xa ,0x0,  0x7, 0x2, 0x1, 0xd,  0x3, 0x6, 0x8, 0x5,  0x9, 0xc, 0xf, 0xe }, 
/* k7 */ { 0xd, 0xb, 0x4 ,0x1,  0x3, 0xf, 0x5, 0x9,  0x0, 0xa, 0xe, 0x7,  0x6, 0x8, 0x2, 0xc }, 
/* k8 */ { 0x1, 0xf, 0xd ,0x0,  0x5, 0x7, 0xa, 0x4,  0x9, 0x2, 0x3, 0xe,  0x6, 0xb, 0x8, 0xc } 
};

/* ��������� ������ ����������� �� ������� ���� 34.11-94
*/
unsigned char GOSThash_example_H0[GOST_HASH_BYTES_SZ] = {
 0x0, 0x0, 0x0, 0x0,  0x0, 0x0, 0x0, 0x0,  0x0, 0x0, 0x0, 0x0,  0x0, 0x0, 0x0, 0x0, 
 0x0, 0x0, 0x0, 0x0,  0x0, 0x0, 0x0, 0x0,  0x0, 0x0, 0x0, 0x0,  0x0, 0x0, 0x0, 0x0 
};

/* ��������� �� ������� ������� ���� 34.11-94
*/
unsigned char GOSThash_example1_M[32] = {
 0x54,0x68,0x69,0x73,  0x20,0x69,0x73,0x20,  0x6D,0x65,0x73,0x73,  0x61,0x67,0x65,0x2C, 
 0x20,0x6C,0x65,0x6E,  0x67,0x74,0x68,0x3D,  0x33,0x32,0x20,0x62,  0x79,0x74,0x65,0x73    
};

/* �������� ����������� ��������� ������� ������� ���� 34.11-94
*/
unsigned char GOSThash_example1_Hash[GOST_HASH_BYTES_SZ]= {
  0xB1,0xC4,0x66,0xD3, 0x75,0x19,0xB8,0x2E, 0x83,0x19,0x81,0x9F, 0xF3,0x25,0x95,0xE0,  
  0x47,0xA2,0x8C,0xB6, 0xF8,0x3E,0xFF,0x1C, 0x69,0x16,0xA8,0x15, 0xA6,0x37,0xFF,0xFA
};

/* ��������� �� ������� ������� ���� 34.11-94
*/
unsigned char GOSThash_example2_M[50] = {
 0x53,0x75,0x70,0x70,  0x6f,0x73,0x65,0x20,  0x74,0x68,0x65,0x20, 0x6f,0x72,0x69,0x67, 
 0x69,0x6e,0x61,0x6c,  0x20,0x6d,0x65,0x73,  0x73,0x61,0x67,0x65, 0x20,0x68,0x61,0x73,
 0x20,0x6c,0x65,0x6e,  0x67,0x74,0x68,0x20,  0x3d,0x20,0x35,0x30, 0x20,0x62,0x79,0x74,
 0x65,0x73  
};

/* �������� ����������� ��������� ������� ������� ���� 34.11-94
*/
unsigned char GOSThash_example2_Hash[GOST_HASH_BYTES_SZ]= {
 0x47,0x1A,0xBA,0x57,  0xA6,0x0A,0x77,0x0D, 0x3A,0x76,0x13,0x06,  0x35,0xC1,0xFB,0xEA,   
 0x4E,0xF1,0x4D,0xE5,  0x1F,0x78,0xb4,0xAE, 0x57,0xDD,0x89,0x3B,  0x62,0xF5,0x52,0x08 
};


/* ����� ���������� ���������� � ������� ���� 34.11-94 ��� ������� �������
*/
unsigned int GOSThash_example1_K1[] = {
  0x33206d54, 0x326c6568, 0x20657369, 0x626e7373, 
  0x79676120, 0x74746769, 0x65686573, 0x733d2c20 
};
unsigned int GOSThash_example1_K2[] = {
    0x4d393320, 0x090d326c, 0x161a2065, 0x1d00626e,
	0x06417967, 0x130e7474, 0x0d166568, 0x110c733d  
};
unsigned int GOSThash_example1_K3[] = {
    0xf513b239, 0x3fa109f2, 0x3abae91a, 0x620c1dff,
	0xc7e1f941, 0x850013f1, 0x730df216, 0x80b111f3
};
unsigned int GOSThash_example1_K4[] = {
    0xa18b0aec, 0xa804c05e, 0xac0cc5ba, 0xee1d620c, 
	0xe7b8c7e1, 0xece27a00, 0xff1b73f2, 0xa0e2804e
};

/* ��������� ���������� �������������� �� ������� ���� 34.11-94
*/
unsigned int test_S[] = {
	0x32bc0b1b, 0x42abbcce, 0x5d9bcffd, 0x5203ebc8, 
	0x00ff0e28, 0x8d345899, 0x0d2a562d, 0xe7860419,
}; 

/* ��������� ��������������� ��������������  �� ������� ���� 34.11-94
*/
unsigned int test_SMix[] = {
    0x3315c034, 0x561c7de3, 0x883da687, 0xd99c4124,
	0x42de7624, 0x68a03b8c, 0x505367a4, 0xcf9a8c65
};


/* ��������� ������������ ��� ��������� ������ ���������� 
*/
static unsigned int gosthash_C[3][GOST_HASH_BYTES_SZ/4] = 
{
	{0x00000000, 0x00000000, 0x00000000, 0x00000000,  0x00000000, 0x00000000, 0x00000000, 0x00000000 },
	{0xFF00FF00, 0xFF00FF00, 0x00FF00FF, 0x00FF00FF,  0x00FFFF00, 0xFF0000FF, 0x000000FF, 0xFF00FFFF },
	{0x00000000, 0x00000000, 0x00000000, 0x00000000,  0x00000000, 0x00000000, 0x00000000, 0x00000000 },
};

int GOSThash_debug = 0;

void GOSThash_print(const char * comments, unsigned char * str );


static void GOSThash_xorstr(unsigned char * dst, const unsigned char * src1, const unsigned char * src2, int len)
{
	register int i;

	for( i = 0; i < len; ++i )
		dst[i] = src1[i] ^ src2[i];

	/*
	for( i = 0; i < len; i += 4 )
		*(int*)(dst + i) = *(int*)(src1 + i) ^ *(int*)(src2 + i);
	*/
}	
/*---------------------------------------------------------------------------*/



static void GOSThash_sumstr(unsigned char * dst, const unsigned char * src, int len)
{
int i;

#ifndef __litle_end__
	unsigned char c = 0;
	for( i = 0; i < len; i ++ )
	{
		dst[i] += src[i] + c;
		if( dst[i] < src[i] )
			c = 1;
		else
			c = 0;	
	}
#else
{
	unsigned int c = 0;
	unsigned int * psrc = (unsigned int*)src;
	unsigned int * pdst = (unsigned int*)dst;

	for( i = 0; i < len/4; i ++ )
	{
		unsigned int a = *psrc++;
		unsigned int b = *pdst;
		c = a + c + b;
		*pdst++ = c;
		c = ((c < a) || (c < b)) ? 1 : 0;
	}
}
#endif	
}	
/*---------------------------------------------------------------------------*/

#if 1
#define  GOSThash_memset  memset
#else
void GOSThash_memset( void * dst, int value, unsigned int len )
{
unsigned char * pdst;

    pdst = (unsigned char*)dst;
	while( len > 0 )
	{
		*pdst++ = (unsigned char)value;
		len --;
	}
}; 
/*---------------------------------------------------------------------------*/
#endif

#if 1
#define  GOSThash_memmove  memmove
#define  GOSThash_memcpy   memcpy
#else
#define  GOSThash_memmove  GOSThash_memcpy

void GOSThash_memcpy( void * dst, void * src, unsigned int len )
{
unsigned char * pdst;
unsigned char * psrc;

    pdst = (unsigned char*)dst;
    psrc = (unsigned char*)src;
	
	while( len > 0 )
	{
		*pdst++ = *psrc++;
		len --;
	}
}; 
#endif
/*---------------------------------------------------------------------------*/


/*
 * Transformation A(X) = (X1 xor X2) || X4 | X3 || X2  
 * X == X4 || X3 || X2 || X1 ==  (b256, b254, ... B1) - 256 bits string 
 * len of src, dst allways 256 / BITS_IN_BYTE
 */
static void GOSThash_A( unsigned char * dst, unsigned char * src)
{
unsigned char buf[GOST_HASH_BYTES_SZ/4];
 
    // save X1
	GOSThash_memcpy( (void*)buf, (void*)src, GOST_HASH_BYTES_SZ/4 );
	    
    // move to left on 256/4 bits
	GOSThash_memmove( (void*)dst, (void*)(src + GOST_HASH_BYTES_SZ/4), (GOST_HASH_BYTES_SZ/4) *3 );
    
    // XOR operation X1(saved in buf) and X2 
    GOSThash_xorstr(dst + GOST_HASH_BYTES_SZ/4*3, buf, dst, GOST_HASH_BYTES_SZ/4);   
} 
/*---------------------------------------------------------------------------*/



/*
 * Transformation P(X),  
 *  x32 || x31 || ... || x1 -> , x_fi(32) || x_fi(31) || .. || x_fi(1)
 *  where fi(i+1 + 4(k-1)) = 8*i + k  
 *  len of src, dst allways 256 / BITS_IN_BYTE
 */
static void GOSThash_P( unsigned char * dst, unsigned char * src)
{
static int index_from[32] = {
   0, 8, 16,24,  1, 9, 17,25,  2, 10, 18, 26,  3, 11, 19, 27,
   4, 12,20,28,  5,13, 21,29,  6, 14, 22, 30,  7, 15, 23, 31
};
int i,j;
unsigned char * psrc;
unsigned char buf[ GOST_HASH_BYTES_SZ ];


	GOSThash_memcpy( (void*)buf, (void*)src, GOST_HASH_BYTES_SZ );
	
	#if	 GOST_HASH_BYTES_SZ / 32 > 1	
    
    for( i = 0; i < 32; i++ )
    {  
		psrc = buf + index_from[i] * GOST_HASH_BYTES_SZ / 32;  
	
		for( j = 0; j <  GOST_HASH_BYTES_SZ / 32; j++ )   
			dst[j] =  psrc[j]; 
			
		dst += GOST_HASH_BYTES_SZ / 32;
   }
	#else
#if defined  __optimized__	
	dst[0]  = buf[0];  dst[1]  = buf[8];   dst[2]  = buf[16];  dst[3]  = buf[24]; 
	dst[4]  = buf[1];  dst[5]  = buf[9];   dst[6]  = buf[17];  dst[7]  = buf[25]; 
	dst[8]  = buf[2];  dst[9]  = buf[10];  dst[10] = buf[18];  dst[11] = buf[26]; 
	dst[12] = buf[3];  dst[13] = buf[11];  dst[14] = buf[19];  dst[15] = buf[27];
	
	dst[16] = buf[4];  dst[17] = buf[12];  dst[18] = buf[20]; dst[19]  = buf[28]; 
	dst[20] = buf[5];  dst[21] = buf[13];  dst[22] = buf[21]; dst[23]  = buf[29]; 
	dst[24] = buf[6];  dst[25] = buf[14];  dst[26] = buf[22]; dst[27] = buf[30]; 
	dst[28] = buf[7];  dst[29] = buf[15];  dst[30] = buf[23]; dst[31] = buf[31];
#else
	for (i = 0, j= 0; i < 32; i+= 4, j++ )
	{
		dst[i]   = buf[j]; 
		dst[i+1] = buf[j+8]; 
		dst[i+2] = buf[j+16]; 
		dst[i+3] = buf[j+24]; 
	}
#endif

	#endif
	
}
/*---------------------------------------------------------------------------*/


/* 
 * generation  four 256 bits keys 
 * H, M points on 256 bits string
*/
static void GOSThash_keygen(const unsigned char * Hi_1, const unsigned char * Mi, unsigned char * K[])
{
unsigned char U[ GOST_HASH_BYTES_SZ ];
unsigned char V[ GOST_HASH_BYTES_SZ ];
unsigned char W[ GOST_HASH_BYTES_SZ ];
int i;
    
	GOSThash_memcpy((void*) U, (void*)Hi_1, GOST_HASH_BYTES_SZ );
	GOSThash_memcpy((void*) V, (void*)Mi,  GOST_HASH_BYTES_SZ );
    
	i = 0;
	while(1)
	{
		GOSThash_xorstr(W, U, V, GOST_HASH_BYTES_SZ);	
       
		GOSThash_P( K[i], W );    
	
		i++;
    	if( i == 4 )
			break; 
    	// new U 
		GOSThash_A(U, U);
		GOSThash_xorstr(U, U, (unsigned char *)gosthash_C[i-1], GOST_HASH_BYTES_SZ );	
	
		// new V
		GOSThash_A(V,V);
		GOSThash_A(V,V);	
    };
}            
/*---------------------------------------------------------------------------*/

/* 
 * gost crypto transformation 
 * H, S points on 256 bits string
 * H - hi-1 hash value or initial value H
 * S - result bit string
 * K - pointers array on gost keys K1, K2, K3, K4  
*/
void GOSThash_enctransform(const unsigned char * H, unsigned char * S, unsigned char * K[],struct  gost_ctx * ctx)
{
int i;

	for( i = 0; i < 4; i++ )
	{
		gost_set_key( ctx, K[i] );

		gost_encrypt( (gost_cblock *)H + i, (gost_cblock *)S + i, ctx,  1 );
	}

}
/*---------------------------------------------------------------------------*/


/*
 * main function mix  trans#include <stdlib.h>
formation	
 * src points on 256 bits string
 * X16 | X15 |...| X2 | X1 -> (X1^X2^X3^X4^X13^X16) | X15 | X14 ... X3 | X2
*/
static void GOSThash_fi( unsigned char * src )
{
#if (GOST_HASH_BYTES_SZ / 16) == 2
unsigned short xr;
#else
unsigned char xr[GOST_HASH_BYTES_SZ / 16];
#endif

#if (GOST_HASH_BYTES_SZ / 16) == 2
	xr = *(short*)src;
	xr ^= *(short*)(src + (GOST_HASH_BYTES_SZ / 16)*1 );  // x1 ^ x2
	xr ^= *(short*)(src + (GOST_HASH_BYTES_SZ / 16)*2 );  // ^ x3
	xr ^= *(short*)(src + (GOST_HASH_BYTES_SZ / 16)*3 );  // ^ x4
	xr ^= *(short*)(src + (GOST_HASH_BYTES_SZ / 16)*12 ); // ^ x13
	xr ^= *(short*)(src + (GOST_HASH_BYTES_SZ / 16)*15 ); // ^ x16
#else	
	GOSThash_xorstr( xr, src, src + (GOST_HASH_BYTES_SZ / 16)*1, GOST_HASH_BYTES_SZ / 16 );  // x1 ^ x2
	GOSThash_xorstr( xr,  xr, src + (GOST_HASH_BYTES_SZ / 16)*2, GOST_HASH_BYTES_SZ / 16 );  // ^ x3
	GOSThash_xorstr( xr,  xr, src + (GOST_HASH_BYTES_SZ / 16)*3, GOST_HASH_BYTES_SZ / 16 );  // ^ x4
	GOSThash_xorstr( xr,  xr, src + (GOST_HASH_BYTES_SZ / 16)*12,GOST_HASH_BYTES_SZ / 16 ); // ^ x13
	GOSThash_xorstr( xr,  xr, src + (GOST_HASH_BYTES_SZ / 16)*15,GOST_HASH_BYTES_SZ / 16 ); // ^ x16
#endif	
	
	GOSThash_memmove( (void*)src, (void*)(src+GOST_HASH_BYTES_SZ / 16), GOST_HASH_BYTES_SZ / 16 * 15 ); 
	
#if (GOST_HASH_BYTES_SZ / 16) == 2	
	*(short*)(src+(GOST_HASH_BYTES_SZ / 16)*15) = xr;
#else
	GOSThash_memcpy( (void*)(src+(GOST_HASH_BYTES_SZ / 16)*15), (void*)xr, GOST_HASH_BYTES_SZ / 16);
#endif
}
/*---------------------------------------------------------------------------*/


/* 
 *  mix transformation 
 * result in Hi 
*/
void GOSThash_mixtransformation(unsigned char * Hi_1, unsigned char * Si, unsigned char * Mi, unsigned char * Hi )
{
unsigned char buf[GOST_HASH_BYTES_SZ ];
int i;

	GOSThash_memcpy( (void*)buf, (void*)Si, GOST_HASH_BYTES_SZ );
	
	for( i = 0; i < 12; i++ )
	{
		GOSThash_fi(buf);
	}
	
	GOSThash_xorstr(buf , buf, Mi, GOST_HASH_BYTES_SZ ); 
	
	GOSThash_fi(buf);
	
	//GOSThash_xorstr(buf, buf, Hi_1, GOST_HASH_BYTES_SZ ); 
	GOSThash_xorstr(Hi , buf, Hi_1, GOST_HASH_BYTES_SZ ); 
	
	for( i = 0; i < 61; i++ )
	{
		//GOSThash_fi(buf);
		GOSThash_fi(Hi);
	}
	
	//GOSThash_memcpy( (void*)Hi, (void*)buf, GOST_HASH_BYTES_SZ );
}
/*---------------------------------------------------------------------------*/


int GOSThash_steptransformation(gost_hashblock * Hi_1, gost_hashblock * Mi, gost_hashblock * Hi, struct gost_ctx * ctx )
{
unsigned char StepKey1[ GOST_KEY_SZ ];
unsigned char StepKey2[ GOST_KEY_SZ ];
unsigned char StepKey3[ GOST_KEY_SZ ];
unsigned char StepKey4[ GOST_KEY_SZ ];
unsigned char * K[4];
unsigned char Si[ GOST_HASH_BYTES_SZ ];
	
	K[0] = StepKey1;
	K[1] = StepKey2;
	K[2] = StepKey3;
	K[3] = StepKey4;

	/* 
	 * GOST encryption transformation 
	 */
	/* GOST key generation */ 
	GOSThash_keygen( (unsigned char *)Hi_1, (unsigned char *)Mi, K );
	if( GOSThash_debug > 0)
	{
		GOSThash_print("K1:", StepKey1 ); 
		GOSThash_print("K2:", StepKey2 ); 
		GOSThash_print("K3:", StepKey3 ); 
		GOSThash_print("K4:", StepKey4 ); 		
	}
	/*GOST 28147-89 encryption  */
	GOSThash_enctransform( (unsigned char *)Hi_1, (unsigned char *)Si, K, ctx );
	if( GOSThash_debug )
		GOSThash_print("Si:", (unsigned char *)Si);

		
	/* 
	 * GOST mix transformation 
	 */
	GOSThash_mixtransformation( (unsigned char *)Hi_1, (unsigned char *)Si, (unsigned char *)Mi, (unsigned char *)Hi );
	
	if( GOSThash_debug )
		GOSThash_print("Hi:", (unsigned char *)Hi);
	
	return 0;
}

void GOSThashTransform( GOSTHASH_CTX * ctx, unsigned char * input)
{
		if( GOSThash_debug )
	    	GOSThash_print("Mi:", input );
		
		GOSThash_sumstr( (unsigned char*)&ctx->Z, (unsigned char*)input, sizeof(gost_hashblock)  );
		if( GOSThash_debug )
			GOSThash_print("Zi:", ctx->Z );
			
		GOSThash_steptransformation( &ctx->Hi, (gost_hashblock*)input, &ctx->Hi, &ctx->gost_enc_ctx );
}


/*
    ���� ���� ���������� ��� ��� ������������������ ������, �� ���� 
	�������� GOSTHASH_INIT, GOSTHASH_Update(), .. ,GOSTHASH_Update(), GOSTHASH_Final()  
*/
int GOSThash_Init( GOSTHASH_CTX * ctx )
{
	if( ctx == NULL )
		return -1;
	
	ctx->datalen[0] = 0;
	ctx->datalen[1] = 0;
	
	GOSThash_memset( (void*)ctx->Z, 0, GOST_HASH_BLOCK_BYTES_SZ ); 
	
	/* ��������,��� ��������� ��� ������ ������� ������
	*/
	GOSThash_memset( (void*)ctx->Hi, 0, GOST_HASH_BYTES_SZ ); 
	
	/* �-����� ��������� ���������� �� ������� ���� 34.11-94
	*/
	kboxinit(&ctx->gost_enc_ctx, &GOSThash_example_kbox);

	return 0; 
}


/* 
   ����� �������� ��� ������ ������ �������� �� ����� ����� ��� ������� ����
   len - ����� data � ������
*/
int GOSThash_Update(GOSTHASH_CTX * ctx, const void * input, unsigned int inputLen)
{
unsigned int i;
unsigned int index, partLen;

    /* �������� ���������� ���� � ������, �������� ���������� �� ����������� ������  
	*/
   index = (unsigned int)((ctx->datalen[0] >> 3) & (GOST_HASH_BLOCK_BYTES_SZ-1));

   /* ������� ���������� ��� � ��������� */
   if ((ctx->datalen[0] += (inputLen << 3)) < (inputLen << 3))
        ctx->datalen[1]++;
   ctx->datalen[1] += (inputLen >> 29);

   /* �������� ������ ���������� ���������� ������   
   */
   partLen = GOST_HASH_BLOCK_BYTES_SZ - index;
      

  /* Transform as many times as possible. */
  if (inputLen >= partLen) {
        GOSThash_memcpy((void*)&ctx->buffer[index], (void*)input, partLen);
		
        GOSThashTransform (ctx, ctx->buffer);

        for (i = partLen; i + GOST_HASH_BLOCK_BYTES_SZ - 1 < inputLen; i += GOST_HASH_BLOCK_BYTES_SZ)
            GOSThashTransform ( ctx, (unsigned char*)input + i );

        index = 0;
  }
  else
        i = 0;

  /* Buffer remaining input */
  GOSThash_memcpy((void*)&ctx->buffer[index], (void*)((char*)input +i), inputLen-i);

  return 0;
}


/*
*/
int GOSThash_Final(GOSTHASH_CTX * ctx, unsigned char * digest )
{
unsigned int index;
unsigned int partLen;
gost_hashblock L; /* sum all blocks lenght */
unsigned char * pchar;

	index = (unsigned int)((ctx->datalen[0] >> 3) & (GOST_HASH_BLOCK_BYTES_SZ-1));

if( index > 0 )
	{
		partLen = GOST_HASH_BLOCK_BYTES_SZ - index;
		
		GOSThash_memset((void*)&ctx->buffer[index],0, partLen);

		GOSThashTransform( ctx, ctx->buffer);
	}

	GOSThash_memset( (void*)L, 0, sizeof(gost_hashblock) );   
	
	pchar = (unsigned char*)&L;
	l2c( ctx->datalen[0], pchar);
	l2c( ctx->datalen[1], pchar);

	if( GOSThash_debug ) 
		printf("Hash with L\n");
	GOSThash_steptransformation( &ctx->Hi, (gost_hashblock*)&L, &ctx->Hi, &ctx->gost_enc_ctx );
	
	if( GOSThash_debug ) 
		printf("Hash with Z\n");	
	GOSThash_steptransformation( &ctx->Hi, &ctx->Z, (gost_hashblock*)digest, &ctx->gost_enc_ctx );
   
	return 0;
}

/*
 * we assume that msg_bits_len < 2^31 
*/
int GOSThash(const unsigned char * M, int msg_bits_len, const gost_hashblock * H0, struct gost_ctx * ctx, gost_hashblock * hash)
{
gost_hashblock Hi;
gost_hashblock L; /* sum all blocks lenght */
gost_hashblock Z; /* sum on module 2^256 all blocks */
gost_hashblock Mlast; 
int i; 
unsigned int len;
unsigned char * pchar;

	// reset   L
	memset( (void*)L, 0, sizeof(gost_hashblock) );   
	memset( (void*)Z, 0, sizeof(gost_hashblock) );   
	
	if( H0 == NULL )
		memset( (void*)Hi, 0, sizeof(gost_hashblock) ); 
	else
		memcpy( (void*)Hi, H0, sizeof(gost_hashblock) ); 
		
		
	len = 0;
	
	for(i = msg_bits_len; i >= sizeof(gost_hashblock)*BITS_IN_BYTE;  i -= sizeof(gost_hashblock)*BITS_IN_BYTE )
	{
		GOSThash_steptransformation( &Hi, (gost_hashblock*)M, &Hi, ctx );
		
		GOSThash_sumstr( (unsigned char*)Z, (unsigned char*)M, sizeof(gost_hashblock)  );
		
		M += sizeof(gost_hashblock);
	}  
	
	if( i > 0 )
	{
		GOSThash_memset( Mlast, 0, sizeof(gost_hashblock) ); 
		GOSThash_memcpy( (void*)Mlast, (void*)M, i / BITS_IN_BYTE );
		
		GOSThash_sumstr( (unsigned char*)Z, (unsigned char*)Mlast, sizeof(gost_hashblock)  );
		
		GOSThash_steptransformation(&Hi, &Mlast, &Hi, ctx );
	}

	pchar = (unsigned char*)&L;
	l2c( msg_bits_len, pchar);

	GOSThash_steptransformation(&Hi, (gost_hashblock*)&L, &Hi, ctx );
	
	GOSThash_steptransformation(&Hi, (gost_hashblock*)&Z, hash, ctx );
	
	return 0;
}


void GOSThash_print(const char * comments, unsigned char * str )
{
int i;
unsigned int value;
unsigned char * pchar;

	printf("%s\n", comments);
	
	for( i = 28; i > 12; i -= 4)
	{
		pchar = &str[i];
		c2l(pchar, value );
		printf(" %08x", value);
	}
	printf("\n");
	
	for(i = 12; i >= 0; i -= 4)
	{
		pchar = &str[i];
		c2l(pchar, value );
		printf( " %08x", value);
	}
	printf("\n");
} 

