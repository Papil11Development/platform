/*  
 * Parameters and constant GOST algo  
 * 
 *
 * Author: Igor V. Moukatchev <mig@papillon.ru>
 *	
 * Copyright (c) 2005 Papillon Sysytem Ltd.
 *
 */

#ifndef HEADER_GOST_H
#define HEADER_GOST_H


/* If this is set to 'unsigned int' on a DEC Alpha, this gives about a
 * %20 speed up (longs are 8 bytes, int's are 4). */
/* Must be unsigned int on ia64/Itanium or DES breaks badly */

#ifdef __KERNEL__
#include <linux/types.h>
#else
#include <sys/types.h>
#endif


typedef unsigned int u32;
typedef unsigned char u8;

#define BITS_IN_BYTE 8


#define c2l(c,l)        (l =((unsigned int)(*((c)++)))    , \
                         l|=((unsigned int)(*((c)++)))<< 8L, \
                         l|=((unsigned int)(*((c)++)))<<16L, \
                         l|=((unsigned int)(*((c)++)))<<24L)

/* NOTE - c is not incremented as per c2l */
#define c2ln(c,l1,l2,n) { \
                        c+=n; \
                        l1=l2=0; \
                        switch (n) { \
                        case 8: l2 =((unsigned int)(*(--(c))))<<24L; \
                        case 7: l2|=((unsigned int)(*(--(c))))<<16L; \
                        case 6: l2|=((unsigned int)(*(--(c))))<< 8L; \
                        case 5: l2|=((unsigned int)(*(--(c))));     \
                        case 4: l1 =((unsigned int)(*(--(c))))<<24L; \
                        case 3: l1|=((unsigned int)(*(--(c))))<<16L; \
                        case 2: l1|=((unsigned int)(*(--(c))))<< 8L; \
                        case 1: l1|=((unsigned int)(*(--(c))));     \
                                } \
                        }

#define l2c(l,c)        (*((c)++)=(unsigned char)(((l)     )&0xff), \
                         *((c)++)=(unsigned char)(((l)>> 8L)&0xff), \
                         *((c)++)=(unsigned char)(((l)>>16L)&0xff), \
                         *((c)++)=(unsigned char)(((l)>>24L)&0xff))


/* GOST constants for generate gamma 
*/
#define C1 0x01010101
#define C2 0x01010104

/* GOST key length 256 bits or 32 bytes
   in algo used how 8 unsigned int words     
*/
#define GOST_KEY_SZ 256/8 





/* GOST block len like DES - 64 bits
*/
typedef unsigned char gost_cblock[8];


struct gost_ctx {
    unsigned int key[8];
     /* Constant s-boxes -- set up in gost_init(). */
    unsigned int k87[256],k65[256],k43[256],k21[256];
};

struct struct_kbox {
	u8 k1[16];
	u8 k2[16];
	u8 k3[16];
	u8 k4[16];
	
	u8 k5[16];
	u8 k6[16];
	u8 k7[16];
	u8 k8[16];
}; 

typedef struct struct_kbox KBOX;

/* defined in gost.c */
void kboxinit(struct gost_ctx *c, KBOX * kbox);
int  gost_set_key(struct gost_ctx * ctx, const unsigned char *key);
void gost_encrypt(gost_cblock *src, gost_cblock *dst, struct gost_ctx * c,  int enc );

/* defined in gost_cbc.c  */
void gost_cbc_encrypt( gost_cblock * input, 
                       gost_cblock * output, 
		       int length,
		       struct gost_ctx * ctx,
		       gost_cblock * ivec,
		       int enc);

#endif
