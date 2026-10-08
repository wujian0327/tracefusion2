TEXT github.com/GoogleCloudPlatform/microservices-demo/src/checkoutservice/genproto.(*productCatalogServiceClient).GetProduct(SB) online-boutique-v0.10.4/src/checkoutservice/genproto/demo_grpc.pb.go
  demo_grpc.pb.go:348	0xa868c0		4c8d6424f8		LEAQ -0x8(SP), R12															
  demo_grpc.pb.go:348	0xa868c5		4d3b6610		CMPQ R12, 0x10(R14)															
  demo_grpc.pb.go:348	0xa868c9		0f8678010000		JBE 0xa86a47																
  demo_grpc.pb.go:348	0xa868cf		55			PUSHQ BP																
  demo_grpc.pb.go:348	0xa868d0		4889e5			MOVQ SP, BP																
  demo_grpc.pb.go:348	0xa868d3		4883c480		ADDQ $-0x80, SP																
  demo_grpc.pb.go:349	0xa868d7		4889842490000000	MOVQ AX, 0x90(SP)															
  demo_grpc.pb.go:349	0xa868df		4889bc24a8000000	MOVQ DI, 0xa8(SP)															
  demo_grpc.pb.go:349	0xa868e7		4889b424b0000000	MOVQ SI, 0xb0(SP)															
  demo_grpc.pb.go:349	0xa868ef		4c898424b8000000	MOVQ R8, 0xb8(SP)															
  demo_grpc.pb.go:349	0xa868f7		48898c24a0000000	MOVQ CX, 0xa0(SP)															
  demo_grpc.pb.go:349	0xa868ff		48899c2498000000	MOVQ BX, 0x98(SP)															
  demo_grpc.pb.go:349	0xa86907		488d05f2671200		LEAQ 0x1267f2(IP), AX															
  demo_grpc.pb.go:349	0xa8690e		e8cd6a99ff		CALL runtime.newobject(SB)														
  demo_grpc.pb.go:349	0xa86913		488d0d56d63900		LEAQ go:itab.google.golang.org/grpc.StaticMethodCallOption,google.golang.org/grpc.CallOption(SB), CX					
  demo_grpc.pb.go:349	0xa8691a		488908			MOVQ CX, 0(AX)																
  demo_grpc.pb.go:349	0xa8691d		488d0d9c599900		LEAQ 0x99599c(IP), CX															
  demo_grpc.pb.go:349	0xa86924		48894808		MOVQ CX, 0x8(AX)															
  demo_grpc.pb.go:349	0xa86928		488b9c24b8000000	MOVQ 0xb8(SP), BX															
  demo_grpc.pb.go:349	0xa86930		488d4b01		LEAQ 0x1(BX), CX															
  demo_grpc.pb.go:349	0xa86934		4883f901		CMPQ CX, $0x1																
  demo_grpc.pb.go:349	0xa86938		770c			JA 0xa86946																
  demo_grpc.pb.go:349	0xa8693a		b901000000		MOVL $0x1, CX																
  demo_grpc.pb.go:349	0xa8693f		ba01000000		MOVL $0x1, DX																
  demo_grpc.pb.go:349	0xa86944		eb25			JMP 0xa8696b																
  demo_grpc.pb.go:349	0xa86946		4889df			MOVQ BX, DI																
  demo_grpc.pb.go:349	0xa86949		488d3530901700		LEAQ 0x179030(IP), SI															
  demo_grpc.pb.go:349	0xa86950		4889cb			MOVQ CX, BX																
  demo_grpc.pb.go:349	0xa86953		b901000000		MOVL $0x1, CX																
  demo_grpc.pb.go:349	0xa86958		e8239c9fff		CALL runtime.growslice(SB)														
  demo_grpc.pb.go:349	0xa8695d		4889ca			MOVQ CX, DX																
  demo_grpc.pb.go:349	0xa86960		4889d9			MOVQ BX, CX																
  demo_grpc.pb.go:349	0xa86963		488b9c24b8000000	MOVQ 0xb8(SP), BX															
  demo_grpc.pb.go:349	0xa8696b		48894c2460		MOVQ CX, 0x60(SP)															
  demo_grpc.pb.go:349	0xa86970		4889442478		MOVQ AX, 0x78(SP)															
  demo_grpc.pb.go:349	0xa86975		4889542468		MOVQ DX, 0x68(SP)															
  demo_grpc.pb.go:349	0xa8697a		48ffc9			DECQ CX																	
  demo_grpc.pb.go:349	0xa8697d		48ffca			DECQ DX																	
  demo_grpc.pb.go:349	0xa86980		48f7da			NEGQ DX																	
  demo_grpc.pb.go:349	0xa86983		48c1fa3f		SARQ $0x3f, DX																
  demo_grpc.pb.go:349	0xa86987		83e210			ANDL $0x10, DX																
  demo_grpc.pb.go:349	0xa8698a		4801c2			ADDQ AX, DX																
  demo_grpc.pb.go:349	0xa8698d		488d05ec8f1700		LEAQ 0x178fec(IP), AX															
  demo_grpc.pb.go:349	0xa86994		488bbc24b0000000	MOVQ 0xb0(SP), DI															
  demo_grpc.pb.go:349	0xa8699c		4889de			MOVQ BX, SI																
  demo_grpc.pb.go:349	0xa8699f		4889d3			MOVQ DX, BX																
  demo_grpc.pb.go:349	0xa869a2		e8795b9fff		CALL runtime.typedslicecopy(SB)														
  demo_grpc.pb.go:350	0xa869a7		488d0512322400		LEAQ 0x243212(IP), AX															
  demo_grpc.pb.go:350	0xa869ae		e82d6a99ff		CALL runtime.newobject(SB)														
  demo_grpc.pb.go:350	0xa869b3		4889442470		MOVQ AX, 0x70(SP)															
  demo_grpc.pb.go:351	0xa869b8		488b942490000000	MOVQ 0x90(SP), DX															
  demo_grpc.pb.go:351	0xa869c0		4c8b02			MOVQ 0(DX), R8																
  demo_grpc.pb.go:351	0xa869c3		488b5208		MOVQ 0x8(DX), DX															
  demo_grpc.pb.go:351	0xa869c7		4d8b4018		MOVQ 0x18(R8), R8															
  demo_grpc.pb.go:351	0xa869cb		4c8b4c2478		MOVQ 0x78(SP), R9															
  demo_grpc.pb.go:351	0xa869d0		4c890c24		MOVQ R9, 0(SP)																
  demo_grpc.pb.go:351	0xa869d4		4c8b4c2460		MOVQ 0x60(SP), R9															
  demo_grpc.pb.go:351	0xa869d9		4c894c2408		MOVQ R9, 0x8(SP)															
  demo_grpc.pb.go:351	0xa869de		4c8b4c2468		MOVQ 0x68(SP), R9															
  demo_grpc.pb.go:351	0xa869e3		4c894c2410		MOVQ R9, 0x10(SP)															
  demo_grpc.pb.go:351	0xa869e8		488b9c2498000000	MOVQ 0x98(SP), BX															
  demo_grpc.pb.go:351	0xa869f0		488b8c24a0000000	MOVQ 0xa0(SP), CX															
  demo_grpc.pb.go:351	0xa869f8		488d3d0b042a00		LEAQ 0x2a040b(IP), DI															
  demo_grpc.pb.go:351	0xa869ff		be2d000000		MOVL $0x2d, SI																
  demo_grpc.pb.go:351	0xa86a04		4c8b8c24a8000000	MOVQ 0xa8(SP), R9															
  demo_grpc.pb.go:351	0xa86a0c		4c8d154df02200		LEAQ 0x22f04d(IP), R10															
  demo_grpc.pb.go:351	0xa86a13		4989c3			MOVQ AX, R11																
  demo_grpc.pb.go:351	0xa86a16		4889d0			MOVQ DX, AX																
  demo_grpc.pb.go:351	0xa86a19		4c89c2			MOVQ R8, DX																
  demo_grpc.pb.go:351	0xa86a1c		4c8d05bdcd1d00		LEAQ 0x1dcdbd(IP), R8															
  demo_grpc.pb.go:351	0xa86a23		ffd2			CALL DX																	
  demo_grpc.pb.go:352	0xa86a25		4885c0			TESTQ AX, AX																
  demo_grpc.pb.go:352	0xa86a28		740e			JE 0xa86a38																
  demo_grpc.pb.go:353	0xa86a2a		4889d9			MOVQ BX, CX																
  demo_grpc.pb.go:353	0xa86a2d		4889c3			MOVQ AX, BX																
  demo_grpc.pb.go:353	0xa86a30		31c0			XORL AX, AX																
  demo_grpc.pb.go:353	0xa86a32		4883ec80		SUBQ $-0x80, SP																
  demo_grpc.pb.go:353	0xa86a36		5d			POPQ BP																	
  demo_grpc.pb.go:353	0xa86a37		c3			RET																	
  demo_grpc.pb.go:355	0xa86a38		488b442470		MOVQ 0x70(SP), AX															
  demo_grpc.pb.go:355	0xa86a3d		31db			XORL BX, BX																
  demo_grpc.pb.go:355	0xa86a3f		31c9			XORL CX, CX																
  demo_grpc.pb.go:355	0xa86a41		4883ec80		SUBQ $-0x80, SP																
  demo_grpc.pb.go:355	0xa86a45		5d			POPQ BP																	
  demo_grpc.pb.go:355	0xa86a46		c3			RET																	
  demo_grpc.pb.go:348	0xa86a47		4889442408		MOVQ AX, 0x8(SP)															
  demo_grpc.pb.go:348	0xa86a4c		48895c2410		MOVQ BX, 0x10(SP)															
  demo_grpc.pb.go:348	0xa86a51		48894c2418		MOVQ CX, 0x18(SP)															
  demo_grpc.pb.go:348	0xa86a56		48897c2420		MOVQ DI, 0x20(SP)															
  demo_grpc.pb.go:348	0xa86a5b		4889742428		MOVQ SI, 0x28(SP)															
  demo_grpc.pb.go:348	0xa86a60		4c89442430		MOVQ R8, 0x30(SP)															
  demo_grpc.pb.go:348	0xa86a65		4c894c2438		MOVQ R9, 0x38(SP)															
  demo_grpc.pb.go:348	0xa86a6a		e8d1db9fff		CALL runtime.morestack_noctxt.abi0(SB)													
  demo_grpc.pb.go:348	0xa86a6f		488b442408		MOVQ 0x8(SP), AX															
  demo_grpc.pb.go:348	0xa86a74		488b5c2410		MOVQ 0x10(SP), BX															
  demo_grpc.pb.go:348	0xa86a79		488b4c2418		MOVQ 0x18(SP), CX															
  demo_grpc.pb.go:348	0xa86a7e		488b7c2420		MOVQ 0x20(SP), DI															
  demo_grpc.pb.go:348	0xa86a83		488b742428		MOVQ 0x28(SP), SI															
  demo_grpc.pb.go:348	0xa86a88		4c8b442430		MOVQ 0x30(SP), R8															
  demo_grpc.pb.go:348	0xa86a8d		4c8b4c2438		MOVQ 0x38(SP), R9															
  demo_grpc.pb.go:348	0xa86a92		e929feffff		JMP github.com/GoogleCloudPlatform/microservices-demo/src/checkoutservice/genproto.(*productCatalogServiceClient).GetProduct(SB)	
