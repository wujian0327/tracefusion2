TEXT main.(*checkoutService).prepOrderItems(SB) online-boutique-v0.10.4/src/checkoutservice/main.go
  main.go:338		0xabbe40		4c8d6424d0		LEAQ -0x30(SP), R12															
  main.go:338		0xabbe45		4d3b6610		CMPQ R12, 0x10(R14)															
  main.go:338		0xabbe49		0f861c030000		JBE 0xabc16b																
  main.go:338		0xabbe4f		55			PUSHQ BP																
  main.go:338		0xabbe50		4889e5			MOVQ SP, BP																
  main.go:338		0xabbe53		4881eca8000000		SUBQ $0xa8, SP																
  main.go:342		0xabbe5a		48898424b8000000	MOVQ AX, 0xb8(SP)															
  main.go:342		0xabbe62		4889bc24d0000000	MOVQ DI, 0xd0(SP)															
  main.go:342		0xabbe6a		48898c24c8000000	MOVQ CX, 0xc8(SP)															
  main.go:342		0xabbe72		4c899424f0000000	MOVQ R10, 0xf0(SP)															
  main.go:342		0xabbe7a		4c898c24e8000000	MOVQ R9, 0xe8(SP)															
  main.go:342		0xabbe82		48899c24c0000000	MOVQ BX, 0xc0(SP)															
  main.go:342		0xabbe8a		4889b424d8000000	MOVQ SI, 0xd8(SP)															
  main.go:339		0xabbe92		488d05471f1c00		LEAQ 0x1c1f47(IP), AX															
  main.go:339		0xabbe99		4889f3			MOVQ SI, BX																
  main.go:339		0xabbe9c		4889d9			MOVQ BX, CX																
  main.go:339		0xabbe9f		90			NOPL																	
  main.go:339		0xabbea0		e8fb459cff		CALL runtime.makeslice(SB)														
  main.go:339		0xabbea5		4889442460		MOVQ AX, 0x60(SP)															
  main.go:340		0xabbeaa		488b9424b8000000	MOVQ 0xb8(SP), DX															
  main.go:340		0xabbeb2		488b7210		MOVQ 0x10(DX), SI															
  demo_grpc.pb.go:335	0xabbeb6		488d3dcb7c3600		LEAQ go:itab.*google.golang.org/grpc.ClientConn,google.golang.org/grpc.ClientConnInterface(SB), DI					
  demo_grpc.pb.go:335	0xabbebd		48897c2468		MOVQ DI, 0x68(SP)															
  demo_grpc.pb.go:335	0xabbec2		4889742470		MOVQ SI, 0x70(SP)															
  demo_grpc.pb.go:335	0xabbec7		31c9			XORL CX, CX																
  main.go:342		0xabbec9		eb1b			JMP 0xabbee6																
  main.go:352		0xabbecb		4c895028		MOVQ R10, 0x28(AX)															
  main.go:353		0xabbecf		4c896030		MOVQ R12, 0x30(AX)															
  main.go:351		0xabbed3		498904d0		MOVQ AX, 0(R8)(DX*8)															
  main.go:342		0xabbed7		488d4a01		LEAQ 0x1(DX), CX															
  main.go:355		0xabbedb		4c89c0			MOVQ R8, AX																
  main.go:347		0xabbede		488b9424b8000000	MOVQ 0xb8(SP), DX															
  main.go:342		0xabbee6		488b9c24d8000000	MOVQ 0xd8(SP), BX															
  main.go:342		0xabbeee		4839cb			CMPQ BX, CX																
  main.go:342		0xabbef1		0f8e64020000		JLE 0xabc15b																
  main.go:342		0xabbef7		48894c2440		MOVQ CX, 0x40(SP)															
  main.go:342		0xabbefc		488bb424d0000000	MOVQ 0xd0(SP), SI															
  main.go:342		0xabbf04		488b3cce		MOVQ 0(SI)(CX*8), DI															
  main.go:342		0xabbf08		48897c2450		MOVQ DI, 0x50(SP)															
  demo.pb.go:79		0xabbf0d		4885ff			TESTQ DI, DI																
  demo.pb.go:79		0xabbf10		740a			JE 0xabbf1c																
  demo.pb.go:80		0xabbf12		4c8b4728		MOVQ 0x28(DI), R8															
  demo.pb.go:80		0xabbf16		4c8b4f30		MOVQ 0x30(DI), R9															
  main.go:343		0xabbf1a		eb06			JMP 0xabbf22																
  main.go:343		0xabbf1c		4531c9			XORL R9, R9																
  main.go:343		0xabbf1f		4531c0			XORL R8, R8																
  main.go:343		0xabbf22		4c894c2438		MOVQ R9, 0x38(SP)															
  main.go:343		0xabbf27		4c89442448		MOVQ R8, 0x48(SP)															
  main.go:343		0xabbf2c		488d05ed9d1c00		LEAQ 0x1c9ded(IP), AX															
  main.go:343		0xabbf33		e8a81496ff		CALL runtime.newobject(SB)														
  main.go:343		0xabbf38		488b4c2438		MOVQ 0x38(SP), CX															
  main.go:343		0xabbf3d		48894830		MOVQ CX, 0x30(AX)															
  main.go:343		0xabbf41		833dd80e960000		CMPL runtime.writeBarrier(SB), $0x0													
  main.go:343		0xabbf48		7507			JNE 0xabbf51																
  main.go:343		0xabbf4a		488b542448		MOVQ 0x48(SP), DX															
  main.go:343		0xabbf4f		eb0d			JMP 0xabbf5e																
  main.go:343		0xabbf51		e82aa49cff		CALL runtime.gcWriteBarrier1(SB)													
  main.go:343		0xabbf56		488b542448		MOVQ 0x48(SP), DX															
  main.go:343		0xabbf5b		498913			MOVQ DX, 0(R11)																
  main.go:343		0xabbf5e		48895028		MOVQ DX, 0x28(AX)															
  main.go:343		0xabbf62		488b9c24c0000000	MOVQ 0xc0(SP), BX															
  main.go:343		0xabbf6a		488b8c24c8000000	MOVQ 0xc8(SP), CX															
  main.go:343		0xabbf72		4889c7			MOVQ AX, DI																
  main.go:343		0xabbf75		31f6			XORL SI, SI																
  main.go:343		0xabbf77		4531c0			XORL R8, R8																
  main.go:343		0xabbf7a		4d89c1			MOVQ R8, R9																
  main.go:343		0xabbf7d		488d442468		LEAQ 0x68(SP), AX															
  main.go:343		0xabbf82		e839a9fcff		CALL github.com/GoogleCloudPlatform/microservices-demo/src/checkoutservice/genproto.(*productCatalogServiceClient).GetProduct(SB)	
  main.go:344		0xabbf87		4885db			TESTQ BX, BX																
  main.go:344		0xabbf8a		0f8551010000		JNE 0xabc0e1																
  demo.pb.go:512	0xabbf90		4885c0			TESTQ AX, AX																
  demo.pb.go:512	0xabbf93		7406			JE 0xabbf9b																
  demo.pb.go:513	0xabbf95		488b5068		MOVQ 0x68(AX), DX															
  main.go:347		0xabbf99		eb02			JMP 0xabbf9d																
  main.go:347		0xabbf9b		31d2			XORL DX, DX																
  main.go:347		0xabbf9d		488b8424b8000000	MOVQ 0xb8(SP), AX															
  main.go:347		0xabbfa5		488b9c24c0000000	MOVQ 0xc0(SP), BX															
  main.go:347		0xabbfad		488b8c24c8000000	MOVQ 0xc8(SP), CX															
  main.go:347		0xabbfb5		4889d7			MOVQ DX, DI																
  main.go:347		0xabbfb8		488bb424e8000000	MOVQ 0xe8(SP), SI															
  main.go:347		0xabbfc0		4c8b8424f0000000	MOVQ 0xf0(SP), R8															
  main.go:347		0xabbfc8		e813020000		CALL main.(*checkoutService).convertCurrency(SB)											
  main.go:348		0xabbfcd		4885db			TESTQ BX, BX																
  main.go:348		0xabbfd0		7566			JNE 0xabc038																
  main.go:347		0xabbfd2		4889442458		MOVQ AX, 0x58(SP)															
  main.go:351		0xabbfd7		488d0522f11d00		LEAQ 0x1df122(IP), AX															
  main.go:351		0xabbfde		6690			NOPW																	
  main.go:351		0xabbfe0		e8fb1396ff		CALL runtime.newobject(SB)														
  main.go:352		0xabbfe5		833d340e960000		CMPL runtime.writeBarrier(SB), $0x0													
  main.go:352		0xabbfec		7519			JNE 0xabc007																
  main.go:351		0xabbfee		488b542440		MOVQ 0x40(SP), DX															
  main.go:351		0xabbff3		4c8b442460		MOVQ 0x60(SP), R8															
  main.go:352		0xabbff8		4c8b542450		MOVQ 0x50(SP), R10															
  main.go:353		0xabbffd		4c8b642458		MOVQ 0x58(SP), R12															
  main.go:352		0xabc002		e9c4feffff		JMP 0xabbecb																
  main.go:351		0xabc007		488b542440		MOVQ 0x40(SP), DX															
  main.go:351		0xabc00c		4c8b442460		MOVQ 0x60(SP), R8															
  main.go:351		0xabc011		4d8b0cd0		MOVQ 0(R8)(DX*8), R9															
  main.go:352		0xabc015		e8c6a39cff		CALL runtime.gcWriteBarrier4(SB)													
  main.go:352		0xabc01a		4c8b542450		MOVQ 0x50(SP), R10															
  main.go:352		0xabc01f		4d8913			MOVQ R10, 0(R11)															
  main.go:353		0xabc022		4c8b642458		MOVQ 0x58(SP), R12															
  main.go:353		0xabc027		4d896308		MOVQ R12, 0x8(R11)															
  main.go:351		0xabc02b		49894310		MOVQ AX, 0x10(R11)															
  main.go:351		0xabc02f		4d894b18		MOVQ R9, 0x18(R11)															
  main.go:352		0xabc033		e993feffff		JMP 0xabbecb																
  demo.pb.go:79		0xabc038		488b4c2450		MOVQ 0x50(SP), CX															
  demo.pb.go:79		0xabc03d		0f1f00			NOPL 0(AX)																
  demo.pb.go:79		0xabc040		4885c9			TESTQ CX, CX																
  demo.pb.go:79		0xabc043		740a			JE 0xabc04f																
  demo.pb.go:80		0xabc045		488b5128		MOVQ 0x28(CX), DX															
  demo.pb.go:80		0xabc049		488b4930		MOVQ 0x30(CX), CX															
  main.go:349		0xabc04d		eb04			JMP 0xabc053																
  main.go:349		0xabc04f		31c9			XORL CX, CX																
  main.go:349		0xabc051		31d2			XORL DX, DX																
  main.go:349		0xabc053		440f117c2478		MOVUPS X15, 0x78(SP)															
  main.go:349		0xabc059		440f11bc2488000000	MOVUPS X15, 0x88(SP)															
  main.go:349		0xabc062		4889d0			MOVQ DX, AX																
  main.go:349		0xabc065		4889cb			MOVQ CX, BX																
  main.go:349		0xabc068		e893f79bff		CALL runtime.convTstring(SB)														
  main.go:349		0xabc06d		488d0d4ca60d00		LEAQ 0xda64c(IP), CX															
  main.go:349		0xabc074		48894c2478		MOVQ CX, 0x78(SP)															
  main.go:349		0xabc079		4889842480000000	MOVQ AX, 0x80(SP)															
  main.go:349		0xabc081		488b8424e8000000	MOVQ 0xe8(SP), AX															
  main.go:349		0xabc089		488b9c24f0000000	MOVQ 0xf0(SP), BX															
  main.go:349		0xabc091		e86af79bff		CALL runtime.convTstring(SB)														
  main.go:349		0xabc096		488d0d23a60d00		LEAQ 0xda623(IP), CX															
  main.go:349		0xabc09d		48898c2488000000	MOVQ CX, 0x88(SP)															
  main.go:349		0xabc0a5		4889842490000000	MOVQ AX, 0x90(SP)															
  main.go:349		0xabc0ad		488d05cb1d2600		LEAQ 0x261dcb(IP), AX															
  main.go:349		0xabc0b4		bb23000000		MOVL $0x23, BX																
  main.go:349		0xabc0b9		488d4c2478		LEAQ 0x78(SP), CX															
  main.go:349		0xabc0be		bf02000000		MOVL $0x2, DI																
  main.go:349		0xabc0c3		4889fe			MOVQ DI, SI																
  main.go:349		0xabc0c6		e8d596a5ff		CALL fmt.Errorf(SB)															
  main.go:349		0xabc0cb		31c9			XORL CX, CX																
  main.go:349		0xabc0cd		4889c7			MOVQ AX, DI																
  main.go:349		0xabc0d0		4889de			MOVQ BX, SI																
  main.go:349		0xabc0d3		31c0			XORL AX, AX																
  main.go:349		0xabc0d5		4889cb			MOVQ CX, BX																
  main.go:349		0xabc0d8		4881c4a8000000		ADDQ $0xa8, SP																
  main.go:349		0xabc0df		5d			POPQ BP																	
  main.go:349		0xabc0e0		c3			RET																	
  demo.pb.go:79		0xabc0e1		488b4c2450		MOVQ 0x50(SP), CX															
  demo.pb.go:79		0xabc0e6		4885c9			TESTQ CX, CX																
  demo.pb.go:79		0xabc0e9		740a			JE 0xabc0f5																
  demo.pb.go:80		0xabc0eb		488b5128		MOVQ 0x28(CX), DX															
  demo.pb.go:80		0xabc0ef		488b4930		MOVQ 0x30(CX), CX															
  main.go:345		0xabc0f3		eb04			JMP 0xabc0f9																
  main.go:345		0xabc0f5		31c9			XORL CX, CX																
  main.go:345		0xabc0f7		31d2			XORL DX, DX																
  main.go:345		0xabc0f9		440f11bc2498000000	MOVUPS X15, 0x98(SP)															
  main.go:345		0xabc102		4889d0			MOVQ DX, AX																
  main.go:345		0xabc105		4889cb			MOVQ CX, BX																
  main.go:345		0xabc108		e8f3f69bff		CALL runtime.convTstring(SB)														
  main.go:345		0xabc10d		488d0daca50d00		LEAQ 0xda5ac(IP), CX															
  main.go:345		0xabc114		48898c2498000000	MOVQ CX, 0x98(SP)															
  main.go:345		0xabc11c		48898424a0000000	MOVQ AX, 0xa0(SP)															
  main.go:345		0xabc124		488d0507812500		LEAQ 0x258107(IP), AX															
  main.go:345		0xabc12b		bb19000000		MOVL $0x19, BX																
  main.go:345		0xabc130		488d8c2498000000	LEAQ 0x98(SP), CX															
  main.go:345		0xabc138		bf01000000		MOVL $0x1, DI																
  main.go:345		0xabc13d		4889fe			MOVQ DI, SI																
  main.go:345		0xabc140		e85b96a5ff		CALL fmt.Errorf(SB)															
  main.go:345		0xabc145		31c9			XORL CX, CX																
  main.go:345		0xabc147		4889c7			MOVQ AX, DI																
  main.go:345		0xabc14a		4889de			MOVQ BX, SI																
  main.go:345		0xabc14d		31c0			XORL AX, AX																
  main.go:345		0xabc14f		4889cb			MOVQ CX, BX																
  main.go:345		0xabc152		4881c4a8000000		ADDQ $0xa8, SP																
  main.go:345		0xabc159		5d			POPQ BP																	
  main.go:345		0xabc15a		c3			RET																	
  main.go:355		0xabc15b		4889d9			MOVQ BX, CX																
  main.go:355		0xabc15e		31ff			XORL DI, DI																
  main.go:355		0xabc160		31f6			XORL SI, SI																
  main.go:355		0xabc162		4881c4a8000000		ADDQ $0xa8, SP																
  main.go:355		0xabc169		5d			POPQ BP																	
  main.go:355		0xabc16a		c3			RET																	
  main.go:338		0xabc16b		4889442408		MOVQ AX, 0x8(SP)															
  main.go:338		0xabc170		48895c2410		MOVQ BX, 0x10(SP)															
  main.go:338		0xabc175		48894c2418		MOVQ CX, 0x18(SP)															
  main.go:338		0xabc17a		48897c2420		MOVQ DI, 0x20(SP)															
  main.go:338		0xabc17f		4889742428		MOVQ SI, 0x28(SP)															
  main.go:338		0xabc184		4c89442430		MOVQ R8, 0x30(SP)															
  main.go:338		0xabc189		4c894c2438		MOVQ R9, 0x38(SP)															
  main.go:338		0xabc18e		4c89542440		MOVQ R10, 0x40(SP)															
  main.go:338		0xabc193		e8a8849cff		CALL runtime.morestack_noctxt.abi0(SB)													
  main.go:338		0xabc198		488b442408		MOVQ 0x8(SP), AX															
  main.go:338		0xabc19d		488b5c2410		MOVQ 0x10(SP), BX															
  main.go:338		0xabc1a2		488b4c2418		MOVQ 0x18(SP), CX															
  main.go:338		0xabc1a7		488b7c2420		MOVQ 0x20(SP), DI															
  main.go:338		0xabc1ac		488b742428		MOVQ 0x28(SP), SI															
  main.go:338		0xabc1b1		4c8b442430		MOVQ 0x30(SP), R8															
  main.go:338		0xabc1b6		4c8b4c2438		MOVQ 0x38(SP), R9															
  main.go:338		0xabc1bb		4c8b542440		MOVQ 0x40(SP), R10															
  main.go:338		0xabc1c0		e97bfcffff		JMP main.(*checkoutService).prepOrderItems(SB)												
