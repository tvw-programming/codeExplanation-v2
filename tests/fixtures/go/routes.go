package main

import (
	"github.com/gofiber/fiber/v2"
	"github.com/gofiber/fiber/v2/middleware/cors"
)

// routes.go registers the HTTP surface for this file's handlers.
func main() {
	app := fiber.New()
	app.Use(cors.New())
	app.Get("/health", healthHandler)

	api := app.Group("/api")
	api.Use(AuthMiddleware)
	v1 := api.Group("/v1")
	v1.Get("/users", listUsers)
	v1.Post("/users", createUser)
}

func AuthMiddleware(c *fiber.Ctx) error {
	return c.Next()
}

func healthHandler(c *fiber.Ctx) error {
	return c.SendString("ok")
}

func listUsers(c *fiber.Ctx) error {
	rows, err := db.Query(c.Context(), "SELECT id FROM users")
	if err != nil {
		return err
	}
	defer rows.Close()
	return c.JSON(rows)
}

func createUser(c *fiber.Ctx) error {
	return c.Status(201).JSON(fiber.Map{"ok": true})
}
