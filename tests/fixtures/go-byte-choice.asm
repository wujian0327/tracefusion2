TEXT main.transform(SB) choice-probe.go
  choice-probe.go:4	0x46fb80		31d2			XORL DX, DX		
  choice-probe.go:4	0x46fb82		eb03			JMP 0x46fb87		
  choice-probe.go:4	0x46fb84		48ffc2			INCQ DX			
  choice-probe.go:4	0x46fb87		4883fa04		CMPQ DX, $0x4		
  choice-probe.go:4	0x46fb8b		7d23			JGE 0x46fbb0		
  choice-probe.go:5	0x46fb8d		803f00			CMPB 0(DI), $0x0	
  choice-probe.go:5	0x46fb90		7510			JNE 0x46fba2		
  choice-probe.go:5	0x46fb92		8400			TESTB AL, 0(AX)		
  choice-probe.go:5	0x46fb94		8403			TESTB AL, 0(BX)		
  choice-probe.go:5	0x46fb96		0fb63413		MOVZX 0(BX)(DX*1), SI	
  choice-probe.go:5	0x46fb9a		40883410		MOVB SI, 0(AX)(DX*1)	
  choice-probe.go:5	0x46fb9e		6690			NOPW			
  choice-probe.go:5	0x46fba0		ebe2			JMP 0x46fb84		
  choice-probe.go:5	0x46fba2		8400			TESTB AL, 0(AX)		
  choice-probe.go:5	0x46fba4		8401			TESTB AL, 0(CX)		
  choice-probe.go:5	0x46fba6		0fb63411		MOVZX 0(CX)(DX*1), SI	
  choice-probe.go:5	0x46fbaa		40883410		MOVB SI, 0(AX)(DX*1)	
  choice-probe.go:5	0x46fbae		ebd4			JMP 0x46fb84		
  choice-probe.go:7	0x46fbb0		c3			RET			
