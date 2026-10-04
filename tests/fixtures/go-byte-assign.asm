TEXT main.transform(SB) fixture/assign.go
  assign.go:4		0x4d9f80		31c9			XORL CX, CX		
  assign.go:4		0x4d9f82		eb0e			JMP 0x4d9f92		
  assign.go:5		0x4d9f84		8400			TESTB AL, 0(AX)		
  assign.go:5		0x4d9f86		8403			TESTB AL, 0(BX)		
  assign.go:5		0x4d9f88		0fb6140b		MOVZX 0(BX)(CX*1), DX	
  assign.go:5		0x4d9f8c		881408			MOVB DL, 0(AX)(CX*1)	
  assign.go:4		0x4d9f8f		48ffc1			INCQ CX			
  assign.go:4		0x4d9f92		4883f904		CMPQ CX, $0x4		
  assign.go:4		0x4d9f96		7cec			JL 0x4d9f84		
  assign.go:7		0x4d9f98		c3			RET			
