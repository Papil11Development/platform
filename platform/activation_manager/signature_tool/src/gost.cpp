
/* 
 * Cryptographic API.
 *
 * Russian encryption alg, used sources by Bruce Shnyer  
 * 
 * 
 * Author: Igor V. Moukatchev <mig@papillon.ru>
 *	
 * Copyright (c) 2005 Papillon Sysytem Ltd.
 *
 */
#include <string.h>

#include "protection/gost.h"

#define __optimized__


/* 
 * Init GOST "s" blocks 
 */
void kboxinit(struct gost_ctx *c, KBOX * kbox)
{
int i;
static u8 k8[16] = {14,  4, 13,  1,   2, 15, 11,  8,   3, 10,  6, 12,   5,  9,  0,  7 };
static u8 k7[16] = {15,  1,  8, 14,   6, 11,  3,  4,   9,  7,  2, 13,  12,  0,  5, 10 };
static u8 k6[16] = {10,  0,  9, 14,   6,  3, 15,  5,   1, 13, 12,  7,  11,  4,  2,  8 };
static u8 k5[16] = { 7, 13, 14,  3,   0,  6,  9, 10,   1,  2,  8,  5,  11, 12,  4, 15 };
static u8 k4[16] = { 2, 12,  4,  1,   7, 10, 11,  6,   8,  5,  3, 15,  13,  0, 14,  9 };
static u8 k3[16] = {12, 1,  10, 15,   9,  2,  6,  8,   0, 13,  3,  4,  14,  7,  5, 11 };
static u8 k2[16] = { 4, 11,  2, 14,  15,  0,  8, 13,   3, 12,  9,  7,   5, 10,  6, 1  };
static u8 k1[16] = {13, 2,   8,  4,   6, 15, 11,  1,  10,  9,  3,  14,  5,  0, 12, 7  };

	if( kbox == NULL )
	{
	for (i = 0; i < 256; i++) 
	{
		c->k87[i] = ((u32)k8[i >> 4] << 4) | k7[i & 15];
		c->k65[i] = ((u32)k6[i >> 4] << 4) | k5[i & 15];
		c->k43[i] = ((u32)k4[i >> 4] << 4) | k3[i & 15];
		c->k21[i] = ((u32)k2[i >> 4] << 4) | k1[i & 15];
	}
	}
	else
	{
	for (i = 0; i < 256; i++) 
	{	
		c->k87[i] = ((u32)kbox->k8[i >> 4] << 4) | kbox->k7[i & 15];
		c->k65[i] = ((u32)kbox->k6[i >> 4] << 4) | kbox->k5[i & 15];
		c->k43[i] = ((u32)kbox->k4[i >> 4] << 4) | kbox->k3[i & 15];
		c->k21[i] = ((u32)kbox->k2[i >> 4] << 4) | kbox->k1[i & 15];
	}
	}

#if defined __optimized__ 	
	for (i = 0; i < 256; i++) 
	{
		c->k87[i] <<= 24;
		c->k65[i] <<= 16;
		c->k43[i] <<= 8;
	}
#endif	
	
}


/* 
 *  Store key in gost_context
 */
int gost_set_key(struct gost_ctx * ctx, const unsigned char *key)
{
int i;
	
	/* expand k block */
	//kboxinit( ctx, NULL );
	
	/* store key */
	for( i= 0; i < 8; i++)
		c2l(key, ctx->key[i] );
		
 
	return 0;
}

/*
 *  GOST round
 */
static inline u32 f(struct gost_ctx *c, u32 x)
{
#if defined __optimized__ 	
	x = ((u32)c->k87[x>>24 & 255]) |
		((u32)c->k65[x>>16 & 255]) |
		((u32)c->k43[x>> 8 & 255]) | (u32)c->k21[x & 255];
#else
	x = ((u32)c->k87[x>>24 & 255] << 24) |
		((u32)c->k65[x>>16 & 255] << 16)  |
		((u32)c->k43[x>> 8 & 255] << 8) | (u32)c->k21[x & 255];
#endif
	
	/* Rotate left 11 bits */
	x = x<<11 | x>>(32-11);
	   
	return x;
}

/* 
 * Encrypt (enc != 0) or decrypt (enc==0) block in ECB
 */
void gost_encrypt(gost_cblock *src, gost_cblock *dst, struct gost_ctx * ctx,  int enc )
{
register unsigned int n1, n2; /* As named in the GOST */
u8 * pchar;
	
	pchar = (u8 *)src;
	c2l(pchar, n1);
	c2l(pchar, n2);
	
	if( enc )
	{
		/* Instead of swapping halves, swap names each round */
		n2 ^= f(ctx, n1+ctx->key[0]);
		n1 ^= f(ctx, n2+ctx->key[1]);
		n2 ^= f(ctx, n1+ctx->key[2]);
		n1 ^= f(ctx, n2+ctx->key[3]);
		n2 ^= f(ctx, n1+ctx->key[4]);
		n1 ^= f(ctx, n2+ctx->key[5]);
		n2 ^= f(ctx, n1+ctx->key[6]);
		n1 ^= f(ctx, n2+ctx->key[7]);

		n2 ^= f(ctx, n1+ctx->key[0]);
		n1 ^= f(ctx, n2+ctx->key[1]);
		n2 ^= f(ctx, n1+ctx->key[2]);
		n1 ^= f(ctx, n2+ctx->key[3]);
		n2 ^= f(ctx, n1+ctx->key[4]);
		n1 ^= f(ctx, n2+ctx->key[5]);
		n2 ^= f(ctx, n1+ctx->key[6]);
		n1 ^= f(ctx, n2+ctx->key[7]);

		n2 ^= f(ctx, n1+ctx->key[0]);
		n1 ^= f(ctx, n2+ctx->key[1]);
		n2 ^= f(ctx, n1+ctx->key[2]);
		n1 ^= f(ctx, n2+ctx->key[3]);
		n2 ^= f(ctx, n1+ctx->key[4]);
		n1 ^= f(ctx, n2+ctx->key[5]);
		n2 ^= f(ctx, n1+ctx->key[6]);
		n1 ^= f(ctx, n2+ctx->key[7]);

		n2 ^= f(ctx, n1+ctx->key[7]);
		n1 ^= f(ctx, n2+ctx->key[6]);
		n2 ^= f(ctx, n1+ctx->key[5]);
		n1 ^= f(ctx, n2+ctx->key[4]);
		n2 ^= f(ctx, n1+ctx->key[3]);
		n1 ^= f(ctx, n2+ctx->key[2]);
		n2 ^= f(ctx, n1+ctx->key[1]);
		n1 ^= f(ctx, n2+ctx->key[0]);
	}
	else
	{
		n2 ^= f(ctx, n1+ctx->key[0]); 
		n1 ^= f(ctx, n2+ctx->key[1]);
		n2 ^= f(ctx, n1+ctx->key[2]); 
		n1 ^= f(ctx, n2+ctx->key[3]);
		n2 ^= f(ctx, n1+ctx->key[4]); 
		n1 ^= f(ctx, n2+ctx->key[5]);
		n2 ^= f(ctx, n1+ctx->key[6]); 
		n1 ^= f(ctx, n2+ctx->key[7]);

		n2 ^= f(ctx, n1+ctx->key[7]);
		n1 ^= f(ctx, n2+ctx->key[6]);
		n2 ^= f(ctx, n1+ctx->key[5]); 
		n1 ^= f(ctx, n2+ctx->key[4]);
		n2 ^= f(ctx, n1+ctx->key[3]);
		n1 ^= f(ctx, n2+ctx->key[2]);
		n2 ^= f(ctx, n1+ctx->key[1]);
		n1 ^= f(ctx, n2+ctx->key[0]);
	
		n2 ^= f(ctx, n1+ctx->key[7]);
		n1 ^= f(ctx, n2+ctx->key[6]);
		n2 ^= f(ctx, n1+ctx->key[5]);
		n1 ^= f(ctx, n2+ctx->key[4]);
		n2 ^= f(ctx, n1+ctx->key[3]);
		n1 ^= f(ctx, n2+ctx->key[2]);
		n2 ^= f(ctx, n1+ctx->key[1]);
		n1 ^= f(ctx, n2+ctx->key[0]);
	
		n2 ^= f(ctx, n1+ctx->key[7]);
		n1 ^= f(ctx, n2+ctx->key[6]);
		n2 ^= f(ctx, n1+ctx->key[5]);
		n1 ^= f(ctx, n2+ctx->key[4]);
		n2 ^= f(ctx, n1+ctx->key[3]);
		n1 ^= f(ctx, n2+ctx->key[2]);
		n2 ^= f(ctx, n1+ctx->key[1]);
		n1 ^= f(ctx, n2+ctx->key[0]);
	}

	pchar = (u8*)dst;
	l2c(n2, pchar ); 
	l2c(n1, pchar ); 
}
	
