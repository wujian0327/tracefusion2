TEXT main.(*checkoutService).convertCurrency(SB) online-boutique-v0.10.4/src/checkoutservice/main.go
  main.go:358		0xabc1e0		493b6610		CMPQ SP, 0x10(R14)														
  main.go:358		0xabc1e4		0f86fd000000		JBE 0xabc2e7															
  main.go:358		0xabc1ea		55			PUSHQ BP															
  main.go:358		0xabc1eb		4889e5			MOVQ SP, BP															
  main.go:358		0xabc1ee		4883ec58		SUBQ $0x58, SP															
  main.go:359		0xabc1f2		4889bc2480000000	MOVQ DI, 0x80(SP)														
  main.go:359		0xabc1fa		4889b42488000000	MOVQ SI, 0x88(SP)														
  main.go:359		0xabc202		4c89842490000000	MOVQ R8, 0x90(SP)														
  main.go:359		0xabc20a		488b4840		MOVQ 0x40(AX), CX														
  demo_grpc.pb.go:651	0xabc20e		488d1573793600		LEAQ go:itab.*google.golang.org/grpc.ClientConn,google.golang.org/grpc.ClientConnInterface(SB), DX				
  demo_grpc.pb.go:651	0xabc215		4889542438		MOVQ DX, 0x38(SP)														
  demo_grpc.pb.go:651	0xabc21a		48894c2440		MOVQ CX, 0x40(SP)														
  main.go:359		0xabc21f		488d057af11d00		LEAQ 0x1df17a(IP), AX														
  main.go:359		0xabc226		e8b51196ff		CALL runtime.newobject(SB)													
  main.go:360		0xabc22b		833dee0b960000		CMPL runtime.writeBarrier(SB), $0x0												
  main.go:360		0xabc232		7512			JNE 0xabc246															
  main.go:360		0xabc234		488b942480000000	MOVQ 0x80(SP), DX														
  main.go:361		0xabc23c		4c8b942488000000	MOVQ 0x88(SP), R10														
  main.go:360		0xabc244		eb1c			JMP 0xabc262															
  main.go:360		0xabc246		e855a19cff		CALL runtime.gcWriteBarrier2(SB)												
  main.go:360		0xabc24b		488b942480000000	MOVQ 0x80(SP), DX														
  main.go:360		0xabc253		498913			MOVQ DX, 0(R11)															
  main.go:361		0xabc256		4c8b942488000000	MOVQ 0x88(SP), R10														
  main.go:361		0xabc25e		4d895308		MOVQ R10, 0x8(R11)														
  main.go:360		0xabc262		48895028		MOVQ DX, 0x28(AX)														
  main.go:361		0xabc266		488b942490000000	MOVQ 0x90(SP), DX														
  main.go:361		0xabc26e		48895038		MOVQ DX, 0x38(AX)														
  main.go:361		0xabc272		4c895030		MOVQ R10, 0x30(AX)														
  main.go:359		0xabc276		488d1d2bb63600		LEAQ go:itab.context.todoCtx,context.Context(SB), BX										
  main.go:359		0xabc27d		488d0d3c009600		LEAQ 0x96003c(IP), CX														
  main.go:359		0xabc284		4889c7			MOVQ AX, DI															
  main.go:359		0xabc287		31f6			XORL SI, SI															
  main.go:359		0xabc289		4531c0			XORL R8, R8															
  main.go:359		0xabc28c		4d89c1			MOVQ R8, R9															
  main.go:359		0xabc28f		488d442438		LEAQ 0x38(SP), AX														
  main.go:359		0xabc294		e8c7abfcff		CALL github.com/GoogleCloudPlatform/microservices-demo/src/checkoutservice/genproto.(*currencyServiceClient).Convert(SB)	
  main.go:362		0xabc299		4885db			TESTQ BX, BX															
  main.go:362		0xabc29c		7443			JE 0xabc2e1															
  main.go:363		0xabc29e		440f117c2448		MOVUPS X15, 0x48(SP)														
  main.go:363		0xabc2a4		7404			JE 0xabc2aa															
  main.go:363		0xabc2a6		488b5b08		MOVQ 0x8(BX), BX														
  main.go:363		0xabc2aa		48895c2448		MOVQ BX, 0x48(SP)														
  main.go:363		0xabc2af		48894c2450		MOVQ CX, 0x50(SP)														
  main.go:363		0xabc2b4		488d050adc2500		LEAQ 0x25dc0a(IP), AX														
  main.go:363		0xabc2bb		bb1f000000		MOVL $0x1f, BX															
  main.go:363		0xabc2c0		488d4c2448		LEAQ 0x48(SP), CX														
  main.go:363		0xabc2c5		bf01000000		MOVL $0x1, DI															
  main.go:363		0xabc2ca		4889fe			MOVQ DI, SI															
  main.go:363		0xabc2cd		e8ce94a5ff		CALL fmt.Errorf(SB)														
  main.go:363		0xabc2d2		4889d9			MOVQ BX, CX															
  main.go:363		0xabc2d5		4889c3			MOVQ AX, BX															
  main.go:363		0xabc2d8		31c0			XORL AX, AX															
  main.go:363		0xabc2da		4883c458		ADDQ $0x58, SP															
  main.go:363		0xabc2de		5d			POPQ BP																
  main.go:363		0xabc2df		90			NOPL																
  main.go:363		0xabc2e0		c3			RET																
  main.go:365		0xabc2e1		4883c458		ADDQ $0x58, SP															
  main.go:365		0xabc2e5		5d			POPQ BP																
  main.go:365		0xabc2e6		c3			RET																
  main.go:358		0xabc2e7		4889442408		MOVQ AX, 0x8(SP)														
  main.go:358		0xabc2ec		48895c2410		MOVQ BX, 0x10(SP)														
  main.go:358		0xabc2f1		48894c2418		MOVQ CX, 0x18(SP)														
  main.go:358		0xabc2f6		48897c2420		MOVQ DI, 0x20(SP)														
  main.go:358		0xabc2fb		4889742428		MOVQ SI, 0x28(SP)														
  main.go:358		0xabc300		4c89442430		MOVQ R8, 0x30(SP)														
  main.go:358		0xabc305		e836839cff		CALL runtime.morestack_noctxt.abi0(SB)												
  main.go:358		0xabc30a		488b442408		MOVQ 0x8(SP), AX														
  main.go:358		0xabc30f		488b5c2410		MOVQ 0x10(SP), BX														
  main.go:358		0xabc314		488b4c2418		MOVQ 0x18(SP), CX														
  main.go:358		0xabc319		488b7c2420		MOVQ 0x20(SP), DI														
  main.go:358		0xabc31e		488b742428		MOVQ 0x28(SP), SI														
  main.go:358		0xabc323		4c8b442430		MOVQ 0x30(SP), R8														
  main.go:358		0xabc328		e9b3feffff		JMP main.(*checkoutService).convertCurrency(SB)											
