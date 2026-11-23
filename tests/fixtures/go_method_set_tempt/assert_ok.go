package tempt

// Explicit compile-time satisfaction — the only allowed Impl proof path.
type Closer interface {
	Close() error
}

type fileHandle struct{}

func (f fileHandle) Close() error { return nil }

var _ Closer = fileHandle{}
var _ Closer = (*fileHandle)(nil)
