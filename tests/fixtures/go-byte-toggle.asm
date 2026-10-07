TEXT main.transform(SB) toggle-probe.go
  toggle-probe.go:4	0x46fb80		31d2			XORL DX, DX		
  toggle-probe.go:4	0x46fb82		eb0c			JMP 0x46fb90		
  toggle-probe.go:5	0x46fb84		0fb637			MOVZX 0(DI), SI		
  toggle-probe.go:5	0x46fb87		83f601			XORL $0x1, SI		
  toggle-probe.go:5	0x46fb8a		408837			MOVB SI, 0(DI)		
  toggle-probe.go:4	0x46fb8d		48ffc2			INCQ DX			
  toggle-probe.go:4	0x46fb90		4883fa04		CMPQ DX, $0x4		
  toggle-probe.go:4	0x46fb94		7d21			JGE 0x46fbb7		
  toggle-probe.go:5	0x46fb96		803f00			CMPB 0(DI), $0x0	
  toggle-probe.go:5	0x46fb99		750e			JNE 0x46fba9		
  toggle-probe.go:5	0x46fb9b		8400			TESTB AL, 0(AX)		
  toggle-probe.go:5	0x46fb9d		8403			TESTB AL, 0(BX)		
  toggle-probe.go:5	0x46fb9f		0fb63413		MOVZX 0(BX)(DX*1), SI	
  toggle-probe.go:5	0x46fba3		40883410		MOVB SI, 0(AX)(DX*1)	
  toggle-probe.go:5	0x46fba7		ebdb			JMP 0x46fb84		
  toggle-probe.go:5	0x46fba9		8400			TESTB AL, 0(AX)		
  toggle-probe.go:5	0x46fbab		8401			TESTB AL, 0(CX)		
  toggle-probe.go:5	0x46fbad		0fb63411		MOVZX 0(CX)(DX*1), SI	
  toggle-probe.go:5	0x46fbb1		40883410		MOVB SI, 0(AX)(DX*1)	
  toggle-probe.go:5	0x46fbb5		ebcd			JMP 0x46fb84		
  toggle-probe.go:7	0x46fbb7		c3			RET			
