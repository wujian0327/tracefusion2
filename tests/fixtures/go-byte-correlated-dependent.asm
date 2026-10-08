TEXT main.transform(SB) scenarios/gin-choice-provenance/correlated-dependent.go
  operations.go:6	0x7513a0		31d2			XORL DX, DX
  operations.go:6	0x7513a2		eb03			JMP 0x7513a7
  operations.go:6	0x7513a4		48ffc2			INCQ DX
  operations.go:6	0x7513a7		4883fa04		CMPQ DX, $0x4
  operations.go:6	0x7513ab		7d23			JGE 0x7513d0
  operations.go:7	0x7513ad		803f00			CMPB 0(DI), $0x0
  operations.go:7	0x7513b0		7510			JNE 0x7513c2
  operations.go:7	0x7513b2		8400			TESTB AL, 0(AX)
  operations.go:7	0x7513b4		8403			TESTB AL, 0(BX)
  operations.go:7	0x7513b6		0fb63413		MOVZX 0(BX)(DX*1), SI
  operations.go:7	0x7513ba		40883410		MOVB SI, 0(AX)(DX*1)
  operations.go:7	0x7513be		6690			NOPW
  operations.go:7	0x7513c0		ebe2			JMP 0x7513a4
  operations.go:7	0x7513c2		8400			TESTB AL, 0(AX)
  operations.go:7	0x7513c4		8401			TESTB AL, 0(CX)
  operations.go:7	0x7513c6		0fb63411		MOVZX 0(CX)(DX*1), SI
  operations.go:7	0x7513ca		40883410		MOVB SI, 0(AX)(DX*1)
  operations.go:7	0x7513ce		ebd4			JMP 0x7513a4
  operations.go:9	0x7513d0		803f00			CMPB 0(DI), $0x0
  operations.go:9	0x7513d3		7504			JNE 0x7513d9
  operations.go:9	0x7513d5		31c9			XORL CX, CX
  operations.go:9	0x7513d7		eb0f			JMP 0x7513e8
  operations.go:12	0x7513d9		c3			RET
  operations.go:10	0x7513da		8400			TESTB AL, 0(AX)
  operations.go:10	0x7513dc		8403			TESTB AL, 0(BX)
  operations.go:10	0x7513de		0fb6140b		MOVZX 0(BX)(CX*1), DX
  operations.go:10	0x7513e2		881408			MOVB DL, 0(AX)(CX*1)
  operations.go:10	0x7513e5		48ffc1			INCQ CX
  operations.go:10	0x7513e8		4883f904		CMPQ CX, $0x4
  operations.go:10	0x7513ec		7cec			JL 0x7513da
  operations.go:10	0x7513ee		ebe9			JMP 0x7513d9
