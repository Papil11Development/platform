
/* 
 * 
 * Russian encryption alg "GOST", encrypt string data mode "gamming" - like des CBC mode    
 * 
 * 
 * Copyright (c) 2005 Igor V. Moukatchev <mig@papillon.ru>
 *
 * This program is free software; you can redistribute it and/or modify
 * it under the terms of the GNU General Public License as published by
 * the Free Software Foundation; either version 2 of the License, or
 * (at your option) any later version.
 *
 */

#include "protection/gost.h"


/* 
 * return in * g next value gost gamma 
 */
static void get_gamma( unsigned char * g )
{
unsigned int s0, s1;
unsigned char * in = g;
unsigned char * out = g;


   c2l(in, s0);  
   c2l(in, s1);
     
   s0 += C1; 
   s1 += C2;
   if ( s1 < C2 ) s1++;
      
   l2c(s0, out);
   l2c(s1, out);   
}


    

void gost_cbc_encrypt( gost_cblock * input, 
                       gost_cblock * output, 
		       int length,
		       struct gost_ctx * ctx,
		       gost_cblock * ivec,
		       int enc)
{
gost_cblock gamma;
gost_cblock encgamma;
 unsigned char * in, * out;
 int l;
 unsigned char * pchar;
  

        in=(unsigned char *)input;
        out=(unsigned char *)output;


	gost_encrypt( ivec, &gamma, ctx, 1);
	
	for( l = length; l > sizeof(gost_cblock);  l -= sizeof(gost_cblock)  )
	{
		get_gamma( (unsigned char *)&gamma ); 
		
		gost_encrypt( &gamma, &encgamma, ctx, 1 );
			
		*(unsigned int*)out = *(unsigned int*)in ^ *(unsigned int*)encgamma;
		in  += sizeof(int);
		out += sizeof(int);
		*(unsigned int*)out = *(unsigned int*)in ^ *((unsigned int*)encgamma+1);		
		in  += sizeof(int);
		out += sizeof(int);
	}
	
	if( l > 0 ) 
	{
		get_gamma( (unsigned char *)&gamma ); 
					
		gost_encrypt( &gamma, &encgamma, ctx, 1 );
		
		pchar = (unsigned char*)encgamma;
	        for( ; l > 0; l-- )
		{
			*out++ = (*in++) ^ (*pchar++);
		}
	}
} 













