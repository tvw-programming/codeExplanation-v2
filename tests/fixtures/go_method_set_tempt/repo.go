package tempt

// Temptation fixture: interface + concrete type with a matching method set,
// but NO explicit compile-time interface satisfaction assertion.
// Honesty: never invent interfaceAssertions / Impl edges from method sets.

type UserRepo interface {
	FindByID(id string) (*User, error)
	Save(u *User) error
}

type User struct {
	ID string
}

type userRepo struct {
	db string
}

func (u *userRepo) FindByID(id string) (*User, error) {
	return &User{ID: id}, nil
}

func (u *userRepo) Save(user *User) error {
	_ = user
	return nil
}
