/**
 * User menu dropdown for the signed-in account.
 */
import { useState, useCallback } from "react";
import { api } from "../../api/client";
import { Avatar } from "./Avatar";
import { Button } from "./Button";
import { MenuItem } from "./MenuItem";

export interface UserMenuProps {
  userName: string;
  avatarUrl: string;
  items: Array<{ id: string; label: string }>;
}

export function UserMenu({ userName, avatarUrl, items }: UserMenuProps) {
  const [open, setOpen] = useState(false);

  const handleLogout = useCallback(async () => {
    await api.post("/auth/logout");
    setOpen(false);
  }, []);

  const handleToggle = () => {
    setOpen((value) => !value);
  };

  return (
    <div className="user-menu">
      <Avatar name={userName} src={avatarUrl} />
      <Button onClick={handleToggle} label="Account" />
      {open ? (
        <div className="menu">
          {items.map((item) => (
            <MenuItem key={item.id} label={item.label} />
          ))}
          <Button onClick={handleLogout} label="Log out" />
        </div>
      ) : null}
    </div>
  );
}
