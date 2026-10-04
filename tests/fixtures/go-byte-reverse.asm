TEXT main.transform(SB) fixture/reverse.go
  reverse.go:4		0x4d9f80		31c9			XORL CX, CX		
  reverse.go:4		0x4d9f82		eb1c			JMP 0x4d9fa0		
  reverse.go:5		0x4d9f84		8400			TESTB AL, 0(AX)		
  reverse.go:5		0x4d9f86		8403			TESTB AL, 0(BX)		
  reverse.go:5		0x4d9f88		488d51fd		LEAQ -0x3(CX), DX	
  reverse.go:5		0x4d9f8c		4889de			MOVQ BX, SI		
  reverse.go:5		0x4d9f8f		4829d6			SUBQ DX, SI		
  reverse.go:5		0x4d9f92		0fb616			MOVZX 0(SI), DX		
  reverse.go:5		0x4d9f95		83f220			XORL $0x20, DX		
  reverse.go:5		0x4d9f98		881408			MOVB DL, 0(AX)(CX*1)	
  reverse.go:4		0x4d9f9b		48ffc1			INCQ CX			
  reverse.go:4		0x4d9f9e		6690			NOPW			
  reverse.go:4		0x4d9fa0		4883f904		CMPQ CX, $0x4		
  reverse.go:4		0x4d9fa4		7cde			JL 0x4d9f84		
  reverse.go:7		0x4d9fa6		c3			RET			
