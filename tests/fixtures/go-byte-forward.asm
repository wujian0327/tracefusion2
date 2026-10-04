TEXT main.transform(SB) fixture/forward.go
  forward.go:4		0x4d9f80		31c9			XORL CX, CX		
  forward.go:4		0x4d9f82		eb11			JMP 0x4d9f95		
  forward.go:5		0x4d9f84		8400			TESTB AL, 0(AX)		
  forward.go:5		0x4d9f86		8403			TESTB AL, 0(BX)		
  forward.go:5		0x4d9f88		0fb6140b		MOVZX 0(BX)(CX*1), DX	
  forward.go:5		0x4d9f8c		83f220			XORL $0x20, DX		
  forward.go:5		0x4d9f8f		881408			MOVB DL, 0(AX)(CX*1)	
  forward.go:4		0x4d9f92		48ffc1			INCQ CX			
  forward.go:4		0x4d9f95		4883f904		CMPQ CX, $0x4		
  forward.go:4		0x4d9f99		7ce9			JL 0x4d9f84		
  forward.go:7		0x4d9f9b		c3			RET			
