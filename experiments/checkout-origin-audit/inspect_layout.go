// Read type layouts from the target ELF only; no application source import.
package main

import (
	"debug/dwarf"
	"debug/elf"
	"encoding/json"
	"fmt"
	"os"
)

func run() error {
	if len(os.Args) < 3 {
		return fmt.Errorf("usage: inspect_layout ELF type-name ...")
	}
	f, err := elf.Open(os.Args[1])
	if err != nil {
		return err
	}
	defer f.Close()
	if f.Machine != elf.EM_X86_64 || f.Type != elf.ET_EXEC {
		return fmt.Errorf("requires amd64 non-PIE ELF")
	}
	d, err := f.DWARF()
	if err != nil {
		return fmt.Errorf("DWARF required: %w", err)
	}
	wanted := map[string]bool{}
	for _, name := range os.Args[2:] {
		wanted[name] = true
	}
	found := map[string]interface{}{}
	r := d.Reader()
	for {
		e, err := r.Next()
		if err != nil {
			return err
		}
		if e == nil {
			break
		}
		if e.Tag != dwarf.TagStructType {
			continue
		}
		name, _ := e.Val(dwarf.AttrName).(string)
		if !wanted[name] {
			continue
		}
		t, err := d.Type(e.Offset)
		if err != nil {
			return err
		}
		st, ok := t.(*dwarf.StructType)
		if !ok {
			return fmt.Errorf("not a struct: %s", name)
		}
		if st.Incomplete {
			continue
		}
		if _, exists := found[name]; exists {
			return fmt.Errorf("ambiguous type: %s", name)
		}
		fields := []map[string]interface{}{}
		for _, field := range st.Field {
			fields = append(fields, map[string]interface{}{"name": field.Name, "offset": field.ByteOffset, "size": field.Type.Size(), "type": field.Type.String()})
		}
		found[name] = map[string]interface{}{"size": st.Size(), "fields": fields}
	}
	for name := range wanted {
		if _, exists := found[name]; !exists {
			return fmt.Errorf("missing named type %s", name)
		}
	}
	return json.NewEncoder(os.Stdout).Encode(found)
}
func main() {
	if err := run(); err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
}
