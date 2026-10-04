TEXT main.transform(SB) fixture/partial/operations.go
  operations.go:4	0x4d9f80		31d2			XORL DX, DX		
  operations.go:4	0x4d9f82		eb0f			JMP 0x4d9f93		
  operations.go:5	0x4d9f84		8400			TESTB AL, 0(AX)		
  operations.go:5	0x4d9f86		8403			TESTB AL, 0(BX)		
  operations.go:5	0x4d9f88		0fb63413		MOVZX 0(BX)(DX*1), SI	
  operations.go:5	0x4d9f8c		40883410		MOVB SI, 0(AX)(DX*1)	
  operations.go:4	0x4d9f90		48ffc2			INCQ DX			
  operations.go:4	0x4d9f93		4883fa04		CMPQ DX, $0x4		
  operations.go:4	0x4d9f97		7ceb			JL 0x4d9f84		
  operations.go:4	0x4d9f99		31d2			XORL DX, DX		
  operations.go:4	0x4d9f9b		eb0e			JMP 0x4d9fab		
  operations.go:8	0x4d9f9d		8400			TESTB AL, 0(AX)		
  operations.go:8	0x4d9f9f		8401			TESTB AL, 0(CX)		
  operations.go:8	0x4d9fa1		0fb61c11		MOVZX 0(CX)(DX*1), BX	
  operations.go:8	0x4d9fa5		881c10			MOVB BL, 0(AX)(DX*1)	
  operations.go:7	0x4d9fa8		48ffc2			INCQ DX			
  operations.go:7	0x4d9fab		4883fa02		CMPQ DX, $0x2		
  operations.go:7	0x4d9faf		7cec			JL 0x4d9f9d		
  operations.go:10	0x4d9fb1		c3			RET			
