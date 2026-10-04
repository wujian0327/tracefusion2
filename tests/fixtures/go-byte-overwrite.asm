TEXT main.transform(SB) fixture/overwrite.go
  overwrite.go:4	0x4d9f80		31d2			XORL DX, DX		
  overwrite.go:4	0x4d9f82		eb0f			JMP 0x4d9f93		
  overwrite.go:5	0x4d9f84		8400			TESTB AL, 0(AX)		
  overwrite.go:5	0x4d9f86		8403			TESTB AL, 0(BX)		
  overwrite.go:5	0x4d9f88		0fb63413		MOVZX 0(BX)(DX*1), SI	
  overwrite.go:5	0x4d9f8c		40883410		MOVB SI, 0(AX)(DX*1)	
  overwrite.go:4	0x4d9f90		48ffc2			INCQ DX			
  overwrite.go:4	0x4d9f93		4883fa04		CMPQ DX, $0x4		
  overwrite.go:4	0x4d9f97		7ceb			JL 0x4d9f84		
  overwrite.go:4	0x4d9f99		31d2			XORL DX, DX		
  overwrite.go:4	0x4d9f9b		eb0e			JMP 0x4d9fab		
  overwrite.go:8	0x4d9f9d		8400			TESTB AL, 0(AX)		
  overwrite.go:8	0x4d9f9f		8401			TESTB AL, 0(CX)		
  overwrite.go:8	0x4d9fa1		0fb61c11		MOVZX 0(CX)(DX*1), BX	
  overwrite.go:8	0x4d9fa5		881c10			MOVB BL, 0(AX)(DX*1)	
  overwrite.go:7	0x4d9fa8		48ffc2			INCQ DX			
  overwrite.go:7	0x4d9fab		4883fa04		CMPQ DX, $0x4		
  overwrite.go:7	0x4d9faf		7cec			JL 0x4d9f9d		
  overwrite.go:10	0x4d9fb1		c3			RET			
