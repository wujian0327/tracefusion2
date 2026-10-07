TEXT main.transform(SB) /fixture/inputs.go
  main.go:3		0x477b80		31d2			XORL DX, DX
  main.go:3		0x477b82		eb03			JMP 0x477b87
  main.go:3		0x477b84		48ffc2			INCQ DX
  main.go:3		0x477b87		4883fa04		CMPQ DX, $0x4
  main.go:3		0x477b8b		7d27			JGE 0x477bb4
  main.go:4		0x477b8d		8407			TESTB AL, 0(DI)
  main.go:4		0x477b8f		0fb63417		MOVZX 0(DI)(DX*1), SI
  main.go:4		0x477b93		4084f6			TESTL SI, SI
  main.go:4		0x477b96		750e			JNE 0x477ba6
  main.go:4		0x477b98		8400			TESTB AL, 0(AX)
  main.go:4		0x477b9a		8403			TESTB AL, 0(BX)
  main.go:4		0x477b9c		0fb63413		MOVZX 0(BX)(DX*1), SI
  main.go:4		0x477ba0		40883410		MOVB SI, 0(AX)(DX*1)
  main.go:4		0x477ba4		ebde			JMP 0x477b84
  main.go:4		0x477ba6		8400			TESTB AL, 0(AX)
  main.go:4		0x477ba8		8401			TESTB AL, 0(CX)
  main.go:4		0x477baa		0fb63411		MOVZX 0(CX)(DX*1), SI
  main.go:4		0x477bae		40883410		MOVB SI, 0(AX)(DX*1)
  main.go:4		0x477bb2		ebd0			JMP 0x477b84
  main.go:6		0x477bb4		c3			RET
