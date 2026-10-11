import Lean.Elab.Import
import Lean.Elab.ParseImportsFast

open Lean Elab

/-!
Print the header of the Lean source on standard input, in the JSON shape of
`lean --deps-json`, as `Lean.Parser.parseHeader` reads it. The REPL imports
what that parser reports. `lean --deps-json` uses a separate fast parser that
can report different imports for the same header.
-/

def main : IO Unit := do
  let input ← IO.FS.readFile "/dev/stdin"
  let (header, _, messages) ← Parser.parseHeader (Parser.mkInputContext input "<stdin>")
  let mut errors := #[]
  for message in messages.toList do
    if message.severity == .error then
      errors := errors.push s!"{message.pos.line}:{message.pos.column}: {← message.data.toString}"
  let result : PrintImportResult :=
    if errors.isEmpty then { result? := some (HeaderSyntax.toModuleHeader header) }
    else { errors }
  IO.println (toJson { imports := #[result] : PrintImportsResult }).compress
