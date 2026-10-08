TEXT github.com/GoogleCloudPlatform/microservices-demo/src/checkoutservice/genproto.(*currencyServiceClient).Convert(SB) online-boutique-v0.10.4/src/checkoutservice/genproto/demo_grpc.pb.go
  demo_grpc.pb.go:664	0xa86e60		4c8d6424f8		LEAQ -0x8(SP), R12													
  demo_grpc.pb.go:664	0xa86e65		4d3b6610		CMPQ R12, 0x10(R14)													
  demo_grpc.pb.go:664	0xa86e69		0f8678010000		JBE 0xa86fe7														
  demo_grpc.pb.go:664	0xa86e6f		55			PUSHQ BP														
  demo_grpc.pb.go:664	0xa86e70		4889e5			MOVQ SP, BP														
  demo_grpc.pb.go:664	0xa86e73		4883c480		ADDQ $-0x80, SP														
  demo_grpc.pb.go:665	0xa86e77		4889842490000000	MOVQ AX, 0x90(SP)													
  demo_grpc.pb.go:665	0xa86e7f		4889bc24a8000000	MOVQ DI, 0xa8(SP)													
  demo_grpc.pb.go:665	0xa86e87		4889b424b0000000	MOVQ SI, 0xb0(SP)													
  demo_grpc.pb.go:665	0xa86e8f		4c898424b8000000	MOVQ R8, 0xb8(SP)													
  demo_grpc.pb.go:665	0xa86e97		48898c24a0000000	MOVQ CX, 0xa0(SP)													
  demo_grpc.pb.go:665	0xa86e9f		48899c2498000000	MOVQ BX, 0x98(SP)													
  demo_grpc.pb.go:665	0xa86ea7		488d0552621200		LEAQ 0x126252(IP), AX													
  demo_grpc.pb.go:665	0xa86eae		e82d6599ff		CALL runtime.newobject(SB)												
  demo_grpc.pb.go:665	0xa86eb3		488d0db6d03900		LEAQ go:itab.google.golang.org/grpc.StaticMethodCallOption,google.golang.org/grpc.CallOption(SB), CX			
  demo_grpc.pb.go:665	0xa86eba		488908			MOVQ CX, 0(AX)														
  demo_grpc.pb.go:665	0xa86ebd		488d0dfc539900		LEAQ 0x9953fc(IP), CX													
  demo_grpc.pb.go:665	0xa86ec4		48894808		MOVQ CX, 0x8(AX)													
  demo_grpc.pb.go:665	0xa86ec8		488b9c24b8000000	MOVQ 0xb8(SP), BX													
  demo_grpc.pb.go:665	0xa86ed0		488d4b01		LEAQ 0x1(BX), CX													
  demo_grpc.pb.go:665	0xa86ed4		4883f901		CMPQ CX, $0x1														
  demo_grpc.pb.go:665	0xa86ed8		770c			JA 0xa86ee6														
  demo_grpc.pb.go:665	0xa86eda		b901000000		MOVL $0x1, CX														
  demo_grpc.pb.go:665	0xa86edf		ba01000000		MOVL $0x1, DX														
  demo_grpc.pb.go:665	0xa86ee4		eb25			JMP 0xa86f0b														
  demo_grpc.pb.go:665	0xa86ee6		4889df			MOVQ BX, DI														
  demo_grpc.pb.go:665	0xa86ee9		488d35908a1700		LEAQ 0x178a90(IP), SI													
  demo_grpc.pb.go:665	0xa86ef0		4889cb			MOVQ CX, BX														
  demo_grpc.pb.go:665	0xa86ef3		b901000000		MOVL $0x1, CX														
  demo_grpc.pb.go:665	0xa86ef8		e883969fff		CALL runtime.growslice(SB)												
  demo_grpc.pb.go:665	0xa86efd		4889ca			MOVQ CX, DX														
  demo_grpc.pb.go:665	0xa86f00		4889d9			MOVQ BX, CX														
  demo_grpc.pb.go:665	0xa86f03		488b9c24b8000000	MOVQ 0xb8(SP), BX													
  demo_grpc.pb.go:665	0xa86f0b		48894c2460		MOVQ CX, 0x60(SP)													
  demo_grpc.pb.go:665	0xa86f10		4889442478		MOVQ AX, 0x78(SP)													
  demo_grpc.pb.go:665	0xa86f15		4889542468		MOVQ DX, 0x68(SP)													
  demo_grpc.pb.go:665	0xa86f1a		48ffc9			DECQ CX															
  demo_grpc.pb.go:665	0xa86f1d		48ffca			DECQ DX															
  demo_grpc.pb.go:665	0xa86f20		48f7da			NEGQ DX															
  demo_grpc.pb.go:665	0xa86f23		48c1fa3f		SARQ $0x3f, DX														
  demo_grpc.pb.go:665	0xa86f27		83e210			ANDL $0x10, DX														
  demo_grpc.pb.go:665	0xa86f2a		4801c2			ADDQ AX, DX														
  demo_grpc.pb.go:665	0xa86f2d		488d054c8a1700		LEAQ 0x178a4c(IP), AX													
  demo_grpc.pb.go:665	0xa86f34		488bbc24b0000000	MOVQ 0xb0(SP), DI													
  demo_grpc.pb.go:665	0xa86f3c		4889de			MOVQ BX, SI														
  demo_grpc.pb.go:665	0xa86f3f		4889d3			MOVQ DX, BX														
  demo_grpc.pb.go:665	0xa86f42		e8d9559fff		CALL runtime.typedslicecopy(SB)												
  demo_grpc.pb.go:666	0xa86f47		488d0512722200		LEAQ 0x227212(IP), AX													
  demo_grpc.pb.go:666	0xa86f4e		e88d6499ff		CALL runtime.newobject(SB)												
  demo_grpc.pb.go:666	0xa86f53		4889442470		MOVQ AX, 0x70(SP)													
  demo_grpc.pb.go:667	0xa86f58		488b942490000000	MOVQ 0x90(SP), DX													
  demo_grpc.pb.go:667	0xa86f60		4c8b02			MOVQ 0(DX), R8														
  demo_grpc.pb.go:667	0xa86f63		488b5208		MOVQ 0x8(DX), DX													
  demo_grpc.pb.go:667	0xa86f67		4d8b4018		MOVQ 0x18(R8), R8													
  demo_grpc.pb.go:667	0xa86f6b		4c8b4c2478		MOVQ 0x78(SP), R9													
  demo_grpc.pb.go:667	0xa86f70		4c890c24		MOVQ R9, 0(SP)														
  demo_grpc.pb.go:667	0xa86f74		4c8b4c2460		MOVQ 0x60(SP), R9													
  demo_grpc.pb.go:667	0xa86f79		4c894c2408		MOVQ R9, 0x8(SP)													
  demo_grpc.pb.go:667	0xa86f7e		4c8b4c2468		MOVQ 0x68(SP), R9													
  demo_grpc.pb.go:667	0xa86f83		4c894c2410		MOVQ R9, 0x10(SP)													
  demo_grpc.pb.go:667	0xa86f88		488b9c2498000000	MOVQ 0x98(SP), BX													
  demo_grpc.pb.go:667	0xa86f90		488b8c24a0000000	MOVQ 0xa0(SP), CX													
  demo_grpc.pb.go:667	0xa86f98		488d3de97e2900		LEAQ 0x297ee9(IP), DI													
  demo_grpc.pb.go:667	0xa86f9f		be24000000		MOVL $0x24, SI														
  demo_grpc.pb.go:667	0xa86fa4		4c8b8c24a8000000	MOVQ 0xa8(SP), R9													
  demo_grpc.pb.go:667	0xa86fac		4c8d150da72000		LEAQ 0x20a70d(IP), R10													
  demo_grpc.pb.go:667	0xa86fb3		4989c3			MOVQ AX, R11														
  demo_grpc.pb.go:667	0xa86fb6		4889d0			MOVQ DX, AX														
  demo_grpc.pb.go:667	0xa86fb9		4c89c2			MOVQ R8, DX														
  demo_grpc.pb.go:667	0xa86fbc		4c8d055d701f00		LEAQ 0x1f705d(IP), R8													
  demo_grpc.pb.go:667	0xa86fc3		ffd2			CALL DX															
  demo_grpc.pb.go:668	0xa86fc5		4885c0			TESTQ AX, AX														
  demo_grpc.pb.go:668	0xa86fc8		740e			JE 0xa86fd8														
  demo_grpc.pb.go:669	0xa86fca		4889d9			MOVQ BX, CX														
  demo_grpc.pb.go:669	0xa86fcd		4889c3			MOVQ AX, BX														
  demo_grpc.pb.go:669	0xa86fd0		31c0			XORL AX, AX														
  demo_grpc.pb.go:669	0xa86fd2		4883ec80		SUBQ $-0x80, SP														
  demo_grpc.pb.go:669	0xa86fd6		5d			POPQ BP															
  demo_grpc.pb.go:669	0xa86fd7		c3			RET															
  demo_grpc.pb.go:671	0xa86fd8		488b442470		MOVQ 0x70(SP), AX													
  demo_grpc.pb.go:671	0xa86fdd		31db			XORL BX, BX														
  demo_grpc.pb.go:671	0xa86fdf		31c9			XORL CX, CX														
  demo_grpc.pb.go:671	0xa86fe1		4883ec80		SUBQ $-0x80, SP														
  demo_grpc.pb.go:671	0xa86fe5		5d			POPQ BP															
  demo_grpc.pb.go:671	0xa86fe6		c3			RET															
  demo_grpc.pb.go:664	0xa86fe7		4889442408		MOVQ AX, 0x8(SP)													
  demo_grpc.pb.go:664	0xa86fec		48895c2410		MOVQ BX, 0x10(SP)													
  demo_grpc.pb.go:664	0xa86ff1		48894c2418		MOVQ CX, 0x18(SP)													
  demo_grpc.pb.go:664	0xa86ff6		48897c2420		MOVQ DI, 0x20(SP)													
  demo_grpc.pb.go:664	0xa86ffb		4889742428		MOVQ SI, 0x28(SP)													
  demo_grpc.pb.go:664	0xa87000		4c89442430		MOVQ R8, 0x30(SP)													
  demo_grpc.pb.go:664	0xa87005		4c894c2438		MOVQ R9, 0x38(SP)													
  demo_grpc.pb.go:664	0xa8700a		e831d69fff		CALL runtime.morestack_noctxt.abi0(SB)											
  demo_grpc.pb.go:664	0xa8700f		488b442408		MOVQ 0x8(SP), AX													
  demo_grpc.pb.go:664	0xa87014		488b5c2410		MOVQ 0x10(SP), BX													
  demo_grpc.pb.go:664	0xa87019		488b4c2418		MOVQ 0x18(SP), CX													
  demo_grpc.pb.go:664	0xa8701e		488b7c2420		MOVQ 0x20(SP), DI													
  demo_grpc.pb.go:664	0xa87023		488b742428		MOVQ 0x28(SP), SI													
  demo_grpc.pb.go:664	0xa87028		4c8b442430		MOVQ 0x30(SP), R8													
  demo_grpc.pb.go:664	0xa8702d		4c8b4c2438		MOVQ 0x38(SP), R9													
  demo_grpc.pb.go:664	0xa87032		e929feffff		JMP github.com/GoogleCloudPlatform/microservices-demo/src/checkoutservice/genproto.(*currencyServiceClient).Convert(SB)	
