/*  
 * Parameters and constant GOST algo  
 * 
 *
 * Author: Igor V. Moukatchev <mig@papillon.ru>
 *	
 * Copyright (c) 2005 Papillon Sysytem Ltd. 
 *
 */

#ifndef HEADER_GOSTHASH_H
#define HEADER_GOSTHASH_H


/* If this is set to 'unsigned int' on a DEC Alpha, this gives about a
 * %20 speed up (longs are 8 bytes, int's are 4). */
/* Must be unsigned int on ia64/Itanium or DES breaks badly */

#ifdef __KERNEL__
#include <linux/types.h>
#else
#include <sys/types.h>
#endif



#define GOST_HASH_BITS_SZ   256 
#define GOST_HASH_BYTES_SZ  (GOST_HASH_BITS_SZ / 8)

#define GOST_HASH_BLOCK_BITS_SZ   256 
#define GOST_HASH_BLOCK_BYTES_SZ  (256/8)



/* GOST hash len  - 256 bits
*/
typedef unsigned char gost_hashblock[ GOST_HASH_BLOCK_BYTES_SZ ];


typedef struct GOSTHASHstate 
{
	unsigned char buffer[GOST_HASH_BLOCK_BYTES_SZ];
	unsigned int datalen[2];
	unsigned char Hi[ GOST_HASH_BLOCK_BYTES_SZ ];
	unsigned char Z[ GOST_HASH_BLOCK_BYTES_SZ ];
	struct gost_ctx gost_enc_ctx;
} GOSTHASH_CTX;

extern unsigned char GOSThash_example1_M[32];
extern unsigned char GOSThash_example1_Hash[GOST_HASH_BYTES_SZ];

extern unsigned char GOSThash_example2_M[50];
extern unsigned char GOSThash_example2_Hash[GOST_HASH_BYTES_SZ];


void GOSThash_print(const char * comments, unsigned char * str );


/* k boxes set by value from GOST 34.11-94 example  
*/
int GOSThash_Init(GOSTHASH_CTX * ctx);
/* 
 * len - length data in bytes 
*/
int GOSThash_Update( GOSTHASH_CTX * ctx, const void * data, unsigned int len );


int GOSThash_Final( GOSTHASH_CTX * ctx, unsigned char * digest ); 


int GOSThash(const unsigned char * M, int msg_bits_len, const gost_hashblock * H0, struct gost_ctx * ctx, gost_hashblock * hash);

#endif
